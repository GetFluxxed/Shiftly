from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.shiftly.app import create_app
from backend.shiftly.identity.primitives import hash_store_code, password_hash
from config import Settings
from database import db_connection


@pytest.fixture
def inventory(isolated_database):
    connect = lambda: psycopg.connect(isolated_database)
    app = create_app(settings=Settings(database_url=isolated_database, secure_cookies=False),
                     connection_factory=connect, provider=lambda *_: {'status': 'accepted'})
    accounts = app.state.context.services.accounts
    service = app.state.context.services.inventory
    with db_connection() as c:
        companies = [c.execute('INSERT INTO businesses(name) VALUES(%s) RETURNING id', (name,)).fetchone()[0] for name in ('Company','Other')]
        stores = [c.execute('INSERT INTO stores(name,access_code_hash,business_id,accounts_enabled) VALUES(%s,%s,%s,true) RETURNING id',
                            (code,hash_store_code(code),companies[0 if n<2 else 1])).fetchone()[0]
                  for n,code in enumerate(('first','second','foreign'))]
        users = {}
        for username, role, grants in [('owner','manager',[]),('manager','manager',[]),('crew','crew',['inventory.view']),
                                       ('noinventory','crew',[]),('delegate','admin',['catalog.manage','inventory.view']),('foreign','manager',[])]:
            uid = c.execute("INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES(%s,%s,'test',%s) RETURNING id",
                            (username,username,password_hash('inventory-password','test'))).fetchone()[0]
            users[username] = uid
            company = companies[1 if username=='foreign' else 0]
            for sid in ([stores[2]] if username=='foreign' else stores[:2]):
                c.execute('INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities) VALUES(%s,%s,%s,%s,%s)',(uid,sid,company,role,grants))
            if username in ('owner','foreign','delegate'):
                c.execute('INSERT INTO business_memberships(user_id,business_id,role,capabilities) VALUES(%s,%s,%s,%s)',
                          (uid,company,'admin' if username=='delegate' else 'owner',grants))
    tokens = {name: accounts.login('foreign' if name=='foreign' else 'first', name, 'inventory-password', client_key=name).token for name in users}
    second = accounts.login('second','owner','inventory-password',client_key='second').token
    with TestClient(app) as client:
        yield SimpleNamespace(service=service, accounts=accounts, client=client, tokens=tokens, second=second,
                              stores=stores, companies=companies, users=users, connect=connect)
