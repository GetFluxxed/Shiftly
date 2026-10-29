"""Identical account policy and credential boundaries through both HTTP transports."""
import http.client
import json
from types import SimpleNamespace

import psycopg
import pytest

import server
from backend.shiftly.identity.accounts import AccountsService
from backend.shiftly.identity.primitives import hash_store_code, hash_token, password_hash
from backend.shiftly.identity.service import IdentityError
from database import db_connection


@pytest.fixture(params=["legacy", "fastapi"])
def account_http(transport_clients, monkeypatch, request):
    fastapi, legacy = transport_clients
    monkeypatch.setattr(server,"validate_report",lambda report:{"status":"accepted"})
    password="synthetic-account-password"
    users,stores,businesses={},[],[]
    salt,digest="parity-salt",password_hash(password,"parity-salt")
    with db_connection() as connection:
        for name in ("Account business","Other business"):
            businesses.append(connection.execute("INSERT INTO businesses(name) VALUES(%s) RETURNING id",(name,)).fetchone()[0])
        for index in range(3):
            bid=businesses[0 if index<2 else 1]
            code=f"account-store-{index}"
            stores.append(connection.execute(
                "INSERT INTO stores(name,access_code_hash,crew_password_hash,business_id,accounts_enabled) VALUES(%s,%s,%s,%s,true) RETURNING id",
                (code,hash_store_code(code),password_hash(password,f"shiftly-crew:{hash_store_code(code)}"),bid),
            ).fetchone()[0])
        for name,role,index,linked in (("owner","manager",0,True),("manager","manager",0,False),
                                       ("crew","crew",0,False),("other","manager",2,True),("minimal","admin",0,False)):
            mid=None
            if linked:
                mid=connection.execute("INSERT INTO manager_users(username,password_salt,password_hash) VALUES(%s,%s,%s) RETURNING id",(name,salt,digest)).fetchone()[0]
                connection.execute("INSERT INTO store_memberships(manager_user_id,store_id) VALUES(%s,%s)",(mid,stores[index]))
                connection.execute("INSERT INTO manager_sessions(token_hash,manager_user_id,store_id,expires_at) VALUES(%s,%s,%s,NOW()+INTERVAL '1 hour')",
                                   (hash_token(f"legacy-{name}"),mid,stores[index]))
            users[name]=connection.execute(
                "INSERT INTO account_users(username,display_name,password_salt,password_hash,legacy_manager_id) VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (name,f"Verified {name}",salt,digest,mid),
            ).fetchone()[0]
            connection.execute("INSERT INTO account_store_memberships(user_id,store_id,business_id,role,capabilities) VALUES(%s,%s,%s,%s,%s)",
                               (users[name],stores[index],businesses[0 if index<2 else 1],role,["inventory.view","counts.submit"] if name=="crew" else []))
        connection.execute("INSERT INTO business_memberships(user_id,business_id,role) VALUES(%s,%s,'owner'),(%s,%s,'admin')",
                           (users["owner"],businesses[0],users["minimal"],businesses[0]))
        connection.execute("INSERT INTO crew_sessions(token_hash,store_id,expires_at) VALUES(%s,%s,NOW()+INTERVAL '1 hour')",(hash_token("shared-crew"),stores[0]))
    accounts=AccountsService(db_connection)
    cookies={name:"shiftly_account_session="+accounts.login(f"account-store-{2 if name=='other' else 0}",name,password,client_key=f"fixture-{name}").token for name in users}
    cookies.update(legacy="shiftly_manager_session=legacy-owner",other_legacy="shiftly_manager_session=legacy-other",shared="shiftly_crew_session=shared-crew")
    host=f"{legacy.server_address[0]}:{legacy.server_address[1]}" if request.param=="legacy" else "testserver"

    def perform(method,path,*,payload=None,raw=None,cookie=None,headers=None):
        body=raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        sent=[("Content-Type","application/json"),*(headers if isinstance(headers,list) else (headers or {}).items())]
        if cookie is not None:
            sent.append(("Cookie",cookie))
        if request.param=="legacy":
            connection=http.client.HTTPConnection(*legacy.server_address,timeout=5)
            try:
                connection.putrequest(method,path)
                for name,value in sent:
                    connection.putheader(name,value)
                if body is not None:
                    connection.putheader("Content-Length",str(len(body)))
                connection.endheaders(body)
                result=connection.getresponse()
                status,data,response_headers=result.status,result.read(),result.getheaders()
            finally:
                connection.close()
        else:
            fastapi.cookies.clear()
            result=fastapi.request(method,path,content=body,headers=sent,follow_redirects=False)
            status,data,response_headers=result.status_code,result.content,result.headers.multi_items()
        return SimpleNamespace(status=status,body=data,headers=response_headers,json=lambda:json.loads(data),
                               cookies=[v.split(";",1)[0] for k,v in response_headers if k.lower()=="set-cookie"])
    return SimpleNamespace(request=perform,accounts=accounts,users=users,stores=stores,businesses=businesses,
                           cookies=cookies,password=password,host=host,transport=request.param,fastapi=fastapi)


def _token(api,name):
    return api.cookies[name].split("=",1)[1]


def _clear_cookie_names(response):
    return {value.partition("=")[0] for name,value in response.headers if name.lower()=="set-cookie" and "Max-Age=0" in value}


def test_account_http_login_exact_identity_cookie_and_status_contract(account_http):
    api=account_http
    login=api.request("POST","/api/accounts/login",payload={"storeCode":"account-store-0","username":" CREW ","password":api.password,
                                                            "role":"owner","userId":api.users["owner"],"storeId":api.stores[2]})
    assert login.status==200,login.body
    actor=login.json()["actor"]
    assert actor["userId"]==api.users["crew"] and actor["storeId"]==api.stores[0] and actor["role"]=="crew"
    assert "token" not in login.json()
    headers=[value for name,value in login.headers if name.lower()=="set-cookie"]
    assert len(headers)==3
    assert all("HttpOnly" in value and "samesite=strict" in value.lower() and "Path=/" in value for value in headers)
    assert _clear_cookie_names(login)=={"shiftly_manager_session","shiftly_crew_session"}
    named=next(value for value in login.cookies if value.startswith("shiftly_account_session="))
    status=api.request("GET","/api/accounts/status",cookie=named)
    assert status.json()["actor"]==actor and status.json()["stores"][0]["storeId"]==api.stores[0]
    oldstatus=api.request("GET","/api/auth/status",cookie=named)
    assert oldstatus.json()=={"authenticated":True,"role":"crew","managerName":None,"actor":actor}
    assert dict((k.lower(),v) for k,v in status.headers)["cache-control"]=="no-store"


def test_account_status_distinguishes_missing_legacy_and_minimal_named(account_http):
    api=account_http
    assert api.request("GET","/api/accounts/status").json()=={"authenticated":False,"reauthenticationRequired":False}
    assert api.request("GET","/api/accounts/status",cookie=api.cookies["legacy"]).status==401
    status=api.request("GET","/api/auth/status",cookie=api.cookies["minimal"])
    assert status.status==200 and status.json()["authenticated"] and status.json()["actor"]["capabilities"]==[]
    for page,expected in (("accounts",200),("inventory",302),("crew",302),("manager",302)):
        assert api.request("GET",f"/{page}.html",cookie=api.cookies["minimal"]).status==expected
    assert api.request("GET","/activate.html").status==200


@pytest.mark.parametrize("case",["named_shared","named_other_manager","named_other_store","invalid_named","empty_named","duplicate_named","bare_named","valid_legacy_pair"])
def test_mixed_cookie_principal_denied_across_all_surfaces(account_http,case):
    api=account_http
    cookies={
        "named_shared":api.cookies["owner"]+"; "+api.cookies["shared"],
        "named_other_manager":api.cookies["owner"]+"; "+api.cookies["other_legacy"],
        "named_other_store":api.cookies["other"]+"; "+api.cookies["legacy"],
        "invalid_named":"shiftly_account_session=invalid; "+api.cookies["legacy"],
        "empty_named":"shiftly_account_session=; "+api.cookies["legacy"],
        "duplicate_named":api.cookies["owner"]+"; "+api.cookies["owner"]+"; "+api.cookies["legacy"],
        "bare_named":"shiftly_account_session; "+api.cookies["legacy"],
        "valid_legacy_pair":api.cookies["legacy"]+"; "+api.cookies["shared"],
    }
    cookie=cookies[case]
    assert api.request("GET","/api/auth/status",cookie=cookie).json()["authenticated"] is False
    for path in ("/api/accounts/status","/api/accounts/team","/api/reports","/api/heads-up","/api/managers","/api/weekly-overview"):
        response=api.request("GET",path,cookie=cookie)
        assert response.status==401,(path,response.status,response.body)
    for page in ("accounts","inventory","manager","crew"):
        assert api.request("GET",f"/{page}.html",cookie=cookie).status==302
    for path,payload in (("/api/accounts/invitations",{"username":"forbidden"}),
                         ("/api/accounts/switch-store",{"storeId":api.stores[1]}),
                         ("/api/reports",{"employee":"Injected","shift":"closing","notes":"A forged mixed session cannot submit this report."}),
                         ("/api/heads-up",{"message":"forbidden"})):
        assert api.request("POST",path,payload=payload,cookie=cookie).status==401
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM account_users WHERE username='forbidden'").fetchone()[0]==0


def test_matching_named_and_legacy_cookies_require_fresh_signin(account_http):
    api=account_http
    for cookie in (api.cookies['owner']+'; '+api.cookies['legacy'],api.cookies['legacy']+'; shiftly_crew_session=expired'):
        assert api.request('GET','/api/accounts/status',cookie=cookie).status==401
        assert api.request('GET','/api/reports',cookie=cookie).status==401


def test_new_manager_without_legacy_id_and_named_crew_reporting(account_http):
    api=account_http
    with db_connection() as connection:
        assert connection.execute("SELECT legacy_manager_id FROM account_users WHERE id=%s",(api.users["manager"],)).fetchone()==(None,)
    response=api.request("POST","/api/reports",cookie=api.cookies["crew"],payload={"employee":"Historical typed text","shift":"opening",
                         "notes":"Replenished the coolers and completed the opening checklist.","storeId":api.stores[2],"actorUserId":api.users["owner"]})
    assert response.status==202,response.body
    with db_connection() as connection:
        assert connection.execute("SELECT store_id,actor_user_id,employee FROM reports").fetchone()==(api.stores[0],api.users["crew"],"Historical typed text")
    listed=api.request("GET","/api/reports",cookie=api.cookies["manager"])
    assert listed.status==200 and listed.json()["reports"][0]["employee"]=="Historical typed text"
    assert api.request("POST","/api/heads-up",cookie=api.cookies["manager"],payload={"message":"Delivery at opening."}).status==200
    assert api.request("GET","/api/heads-up",cookie=api.cookies["crew"]).json()["message"]=="Delivery at opening."
    assert api.request("GET","/api/reports",cookie=api.cookies["other"]).json()["reports"]==[]
    assert api.request("POST","/api/heads-up",cookie=api.cookies["crew"],payload={"message":"No authority"}).status==401


def test_camel_case_lifecycle_invite_reissue_activate_membership_switch_password(account_http):
    api=account_http
    invited=api.request("POST","/api/accounts/invitations",cookie=api.cookies["owner"],payload={"username":"new-crew","displayName":"New Crew",
                        "role":"crew","capabilities":[],"storeId":api.stores[1],"expiresIn":120,"reason":"Scoped invitation."})
    assert invited.status==200,invited.body
    user_id=invited.json()["userId"]
    replaced=api.request("POST","/api/accounts/invitations/reissue",cookie=api.cookies["owner"],payload={"userId":user_id,"storeId":api.stores[1],"expiresIn":180,"reason":"Replacement invitation."})
    assert replaced.status==200,replaced.body
    assert api.request("POST","/api/accounts/activate",payload={"token":invited.json()["token"],"password":api.password}).status==400
    activated=api.request("POST","/api/accounts/activate",payload={"token":replaced.json()["token"],"password":api.password})
    assert activated.status==200,activated.body
    assert activated.json()["actor"]["storeId"]==api.stores[1]
    assert activated.json()["actor"]["displayName"]=="New Crew"
    cookie=activated.cookies[0]
    assert api.request("POST","/api/accounts/activate",payload={"token":replaced.json()["token"],"password":api.password}).status==400
    changed=api.request("POST","/api/accounts/memberships",cookie=api.cookies["owner"],payload={"userId":user_id,"role":"crew",
                        "capabilities":["inventory.view"],"active":True,"storeId":api.stores[0],"reason":"Second store."})
    assert changed.status==409,changed.body
    assert api.request('POST','/api/accounts/switch-store',cookie=cookie,payload={'storeId':api.stores[0]}).status==403
    removed=api.request('POST','/api/accounts/memberships',cookie=api.cookies['owner'],payload={'userId':user_id,'role':'crew','active':False,'storeId':api.stores[1]})
    assert removed.status==200
    changed=api.request('POST','/api/accounts/memberships',cookie=api.cookies['owner'],payload={'userId':user_id,'role':'crew','active':True,'storeId':api.stores[0]})
    assert changed.status==200
    assert api.request('GET','/api/accounts/status',cookie=cookie).status==401
    fresh=api.request('POST','/api/accounts/login',payload={'username':'new-crew','password':api.password}).cookies[0]
    changed=api.request("POST","/api/accounts/password",cookie=fresh,payload={"currentPassword":api.password,"newPassword":"synthetic-new-password"})
    assert changed.status==200,changed.body
    assert _clear_cookie_names(changed)=={"shiftly_account_session","shiftly_manager_session","shiftly_crew_session"}
    assert api.request("GET","/api/accounts/status",cookie=fresh).status==401
    assert api.request("POST","/api/accounts/login",payload={"storeCode":"account-store-0","username":"new-crew","password":"synthetic-new-password"}).status==200


def test_business_delegation_suspension_cutover_transfer(account_http):
    api=account_http
    owner=api.cookies["owner"]
    result=api.request("POST","/api/accounts/business-memberships",cookie=owner,payload={"userId":api.users["manager"],"role":"admin",
                       "capabilities":["catalog.manage"],"active":True,"reason":"Catalog delegation."})
    assert result.status==200,result.body
    result=api.request("POST","/api/accounts/suspend",cookie=owner,payload={"userId":api.users["crew"],"suspended":True,"reason":"Synthetic suspension."})
    assert result.status==200 and result.json()["state"]=="suspended"
    assert api.request("GET","/api/accounts/status",cookie=api.cookies["crew"]).status==401
    assert api.request("POST","/api/accounts/suspend",cookie=owner,payload={"userId":api.users["crew"],"suspended":False,"reason":"Synthetic reactivation."}).status==200
    result=api.request("POST","/api/accounts/cutover",cookie=owner,payload={"storeId":api.stores[0],"reason":"Individual enrollment ready."})
    assert result.status==200 and not result.json()["sharedCrewEnabled"]
    assert api.request("GET","/api/auth/status",cookie=api.cookies["shared"]).json()["authenticated"] is False
    result=api.request("POST","/api/accounts/transfer-ownership",cookie=owner,payload={"userId":api.users["manager"],"reason":"Explicit transfer."})
    assert result.status==200,result.body
    assert len(_clear_cookie_names(result))==3
    assert api.request("GET","/api/accounts/status",cookie=owner).status==401


def test_operator_reset_redemption_replay_and_logout_revoke_all_cookie_types(account_http):
    api=account_http
    reset=api.accounts.issue_password_reset(user_id=api.users["crew"],reason="Verified synthetic recovery.")
    recovered=api.request("POST","/api/accounts/reset-password",payload={"token":reset["token"],"password":"recovered-password"})
    assert recovered.status==200 and recovered.json()["reauthenticationRequired"]
    assert len(_clear_cookie_names(recovered))==3
    assert api.request("POST","/api/accounts/reset-password",payload={"token":reset["token"],"password":"another-password"}).status==400
    assert api.request("GET","/api/accounts/status",cookie=api.cookies["crew"]).status==401
    combined=api.cookies["owner"]+"; "+api.cookies["legacy"]+"; "+api.cookies["shared"]
    logout=api.request("POST","/api/accounts/logout",cookie=combined)
    assert logout.status==200 and len(_clear_cookie_names(logout))==3
    for key in ("owner","legacy","shared"):
        assert api.request("GET","/api/auth/status",cookie=api.cookies[key]).json()["authenticated"] is False


@pytest.mark.parametrize("operation",["login","activate","reset-password","logout","invitations"])
def test_account_mutations_reject_cross_origin_even_public_actions(account_http,operation):
    api=account_http
    for headers in ({"Origin":"https://attacker.invalid"},{"Sec-Fetch-Site":"cross-site"}):
        response=api.request("POST",f"/api/accounts/{operation}",payload={},cookie=api.cookies["owner"],headers=headers)
        assert response.status==403 and response.json()["error"]=="Cross-origin account changes are not permitted."
    # Same-site is not cross-site; an exact supplied Origin still must match Host.
    response=api.request("POST","/api/accounts/logout",headers={"Origin":f"http://{api.host}","Sec-Fetch-Site":"same-site"})
    assert response.status==200


@pytest.mark.parametrize("raw",[b"[]",b"{",b"",b"x"*20_001])
def test_account_bodies_have_consistent_bounds_and_errors(account_http,raw):
    response=account_http.request("POST","/api/accounts/invitations",cookie=account_http.cookies["owner"],raw=raw)
    assert response.status==400 and response.json()=={"error":"Invalid account request."}


@pytest.mark.parametrize("path,fields",[("/api/reports",{"employee":"Stale tab","shift":"closing","notes":"This report belongs to the previously selected store."}),
                                        ("/api/heads-up",{"message":"Stale message"}),
                                        ("/api/accounts/invitations",{"username":"stale-invite"}),
                                        ("/api/accounts/switch-store",{"storeId":1})])
def test_stale_store_precondition_fails_without_any_write(account_http,path,fields):
    api=account_http
    wrong=api.request("POST",path,cookie=api.cookies["owner"],payload={**fields,"expectedStoreId":api.stores[2]})
    assert wrong.status==409,wrong.body
    assert wrong.json()["error"]=="The selected store changed. Refresh and try again."
    invalid=api.request("POST",path,cookie=api.cookies["owner"],payload={**fields,"expectedStoreId":True})
    assert invalid.status==400
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM store_heads_up").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM account_users WHERE username='stale-invite'").fetchone()[0]==0


def test_account_database_errors_are_sanitized(account_http,monkeypatch):
    api=account_http
    def unavailable(*args,**kwargs):
        raise psycopg.OperationalError("password=do-not-expose database-private-host")
    monkeypatch.setattr(AccountsService,"login_payload",unavailable)
    response=api.request("POST","/api/accounts/login",payload={"storeCode":"account-store-0","username":"owner","password":api.password})
    assert response.status==503 and response.json()=={"error":"Account service is temporarily unavailable."}
    assert "do-not-expose" not in response.body.decode()


def test_explicit_legacy_login_replaces_named_and_other_legacy_cookies(account_http):
    api=account_http
    response=api.request("POST","/api/auth/login",cookie="shiftly_account_session=expired; "+api.cookies["shared"],
                         payload={"username":"owner","password":api.password})
    assert response.status==200,response.body
    assert response.cookies[0].startswith("shiftly_account_session=")
    assert _clear_cookie_names(response)=={"shiftly_manager_session","shiftly_crew_session"}
    assert api.request("GET","/api/auth/status",cookie=response.cookies[0]).json()["role"]=="manager"


@pytest.mark.parametrize("kind",["named_crew","legacy_crew","legacy_manager"])
def test_report_authorization_is_rechecked_after_quality_gate(account_http,monkeypatch,kind):
    api=account_http
    calls=[]
    def revoke(report):
        calls.append("quality")
        if kind=="named_crew":
            api.accounts.set_membership(_token(api,"owner"),user_id=api.users["crew"],role="crew",active=False,reason="Revoke during quality check.")
        elif kind=="legacy_crew":
            api.accounts.cutover_store(_token(api,"owner"),reason="Cutover during quality check.")
        else:
            api.accounts.change_password(_token(api,"owner"),current_password=api.password,new_password="changed-during-quality")
        return {"status":"accepted"}
    monkeypatch.setattr(server,"validate_report",revoke)
    monkeypatch.setattr(api.fastapi.app.state.context.services.submission,"quality_gate",revoke)
    key={"named_crew":"crew","legacy_crew":"shared","legacy_manager":"legacy"}[kind]
    response=api.request("POST","/api/reports",cookie=api.cookies[key],payload={"employee":"Race report","shift":"closing",
                         "notes":"Completed the detailed handoff before credentials changed."})
    assert response.status in {401,403},response.body
    assert calls==(["quality"] if kind=="named_crew" else [])
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM reports").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM briefing_jobs").fetchone()[0]==0


@pytest.mark.parametrize("kind",["named","legacy"])
def test_heads_up_write_rechecks_current_session(account_http,monkeypatch,kind):
    from backend.shiftly.identity.repository import IdentityRepository
    from backend.shiftly.stores.service import StoresService
    api=account_http
    original=StoresService.save_heads_up
    def revoke_then_save(service,*args,**kwargs):
        if kind=="named":
            api.accounts.logout(_token(api,"manager"))
        else:
            IdentityRepository(db_connection).logout("legacy-owner","")
        return original(service,*args,**kwargs)
    monkeypatch.setattr(StoresService,"save_heads_up",revoke_then_save)
    response=api.request("POST","/api/heads-up",cookie=api.cookies["manager" if kind=="named" else "legacy"],payload={"message":"Cannot persist after logout."})
    assert response.status in {401,403},response.body
    with db_connection() as connection:
        assert connection.execute("SELECT count(*) FROM store_heads_up").fetchone()[0]==0


def test_logout_all_revokes_other_named_sessions_and_clears_all_cookies(account_http):
    api=account_http
    second=api.accounts.login("account-store-0","crew",api.password,client_key="another-device")
    result=api.request("POST","/api/accounts/logout-all",cookie=api.cookies["crew"],payload={})
    assert result.status==200 and len(_clear_cookie_names(result))==3
    for token in (_token(api,"crew"),second.token):
        with pytest.raises(IdentityError):
            api.accounts.resolve_actor(token)


@pytest.mark.parametrize("second",["duplicate_named","conflicting_legacy","malformed_named"])
def test_physical_cookie_headers_preserve_conflicts_and_named_presence(account_http,second):
    api=account_http
    headers=[("Cookie",api.cookies["owner"]),
             ("Cookie",api.cookies["owner"] if second=="duplicate_named" else api.cookies["other_legacy"] if second=="conflicting_legacy" else "shiftly_account_session")]
    for path in ("/api/accounts/status","/api/accounts/team","/api/reports"):
        result=api.request("GET",path,headers=headers)
        assert result.status==401,(path,result.body)
    assert api.request("GET","/accounts.html",headers=headers).status==302
    status=api.request("GET","/api/auth/status",headers=headers)
    assert status.status==200 and status.json()["authenticated"] is False
