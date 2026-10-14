"""Developer setup cannot overwrite a workspace or become a public signup path."""
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.runtime.demo import create_demo_workspace, demo_connection_string


@pytest.mark.parametrize('dsn', [
    '',
    'postgresql://operator:secret@remote.example:5432/shiftly_demo_sample',
    'postgresql://operator:secret@localhost:5432/shiftly',
    'host=localhost dbname=shiftly_demo_sample user=operator',
    'host=localhost port=5432 dbname=shiftly_demo_sample user=operator hostaddr=192.0.2.1',
    'service=production host=localhost port=5432 dbname=shiftly_demo_sample user=operator',
])
def test_demo_target_refuses_implicit_or_non_demo_destinations(dsn):
    with pytest.raises(ValueError) as error:
        demo_connection_string(dsn)
    assert 'secret' not in str(error.value)


def test_demo_target_uses_explicit_loopback_database():
    fields = conninfo_to_dict(demo_connection_string(
        'postgresql://operator:local-test@127.0.0.1:55438/shiftly_demo_sample'))
    assert fields['dbname'] == 'shiftly_demo_sample'
    assert fields['host'] == '127.0.0.1' and fields['connect_timeout'] == '5'


def test_empty_demo_owner_can_sign_in_and_repeated_setup_preserves_data(isolated_database):
    connect = lambda: psycopg.connect(isolated_database)
    result = create_demo_workspace(connect, 'my-local-demo-password')
    account = AccountsService(connect).login(None, 'demo-owner', 'my-local-demo-password', client_key='demo-test')
    with connect() as connection:
        actor = AccountsService(connect).require(account.token, 'inventory.view', connection=connection)
    assert actor.role == 'owner' and actor.store_id == result['storeId']
    with pytest.raises(ValueError, match='already contains'):
        create_demo_workspace(connect, 'replacement-password')
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM account_users').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM inventory_stock_balances').fetchone()[0] == 0
        assert connection.execute('SELECT shared_crew_enabled FROM stores').fetchone()[0] is False
        assert connection.execute('SELECT count(*) FROM account_audit WHERE action=%s',
                                  ('demo.workspace_initialized',)).fetchone()[0] == 1
    AccountsService(connect).login(None, 'demo-owner', 'my-local-demo-password', client_key='demo-retry')


def test_concurrent_demo_initialization_creates_exactly_one_workspace(isolated_database):
    connect = lambda: psycopg.connect(isolated_database)
    def initialize():
        try:
            create_demo_workspace(connect, 'concurrent-local-password')
            return 'created'
        except ValueError as error:
            assert 'already contains' in str(error)
            return 'refused'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: initialize(), range(2))) == ['created', 'refused']
    with connect() as connection:
        assert connection.execute('SELECT count(*) FROM businesses').fetchone()[0] == 1


def test_invalid_demo_password_does_not_connect():
    def forbidden():
        pytest.fail('Invalid input opened a database connection')
    with pytest.raises(ValueError, match='password'):
        create_demo_workspace(forbidden, 'short')


def test_demo_partial_setup_failure_rolls_back_every_insert(isolated_database, monkeypatch):
    from backend.shiftly.runtime import demo
    connect = lambda: psycopg.connect(isolated_database)
    def fail_hash(*args):
        raise RuntimeError('Synthetic failure after store insertion')
    monkeypatch.setattr(demo, 'password_hash', fail_hash)
    with pytest.raises(RuntimeError, match='Synthetic failure'):
        create_demo_workspace(connect, 'rollback-test-password')
    with connect() as connection:
        for table in ('businesses', 'stores', 'account_users', 'business_memberships', 'account_audit'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_demo_cli_refuses_noninteractive_input_before_reading_password(monkeypatch):
    from backend.shiftly.runtime import demo
    monkeypatch.setenv('DEMO_DATABASE_URL', 'postgresql://operator@localhost:55438/shiftly_demo_test')
    monkeypatch.setattr(demo.sys.stdin, 'isatty', lambda: False)
    monkeypatch.setattr(demo.getpass, 'getpass', lambda *_: pytest.fail('Read a noninteractive secret'))
    with pytest.raises(SystemExit, match='interactive terminal'):
        demo.main(['--create-empty-workspace'])


def test_demo_cli_refuses_echo_fallback(monkeypatch):
    import warnings
    from backend.shiftly.runtime import demo
    monkeypatch.setenv('DEMO_DATABASE_URL', 'postgresql://operator@localhost:55438/shiftly_demo_test')
    monkeypatch.setattr(demo.sys.stdin, 'isatty', lambda: True)
    def echo_fallback(*args):
        warnings.warn('Cannot hide terminal input', demo.getpass.GetPassWarning)
        pytest.fail('Warning did not abort before reading input')
    monkeypatch.setattr(demo.getpass, 'getpass', echo_fallback)
    with pytest.raises(SystemExit, match='Secure password input is unavailable'):
        demo.main(['--create-empty-workspace'])
