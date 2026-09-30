"""Heads Up keeps one store-scoped policy across browser and native transports."""

import pytest

from backend.shiftly.identity.primitives import password_hash
from backend.shiftly.stores.service import StoresService
from database import db_connection
from tests.transport_parity.test_accounts_parity import account_http
from tests.transport_parity.test_mobile_api import mobile


def _native_manager(mobile):
    """Add a manager without changing the shared mobile fixture's role matrix."""
    salt = "heads-up-manager-salt"
    with db_connection() as connection:
        user_id = connection.execute(
            """INSERT INTO account_users(username,display_name,password_salt,password_hash)
               VALUES('heads-up-manager','Heads Up Manager',%s,%s) RETURNING id""",
            (salt, password_hash(mobile.password, salt)),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO account_store_memberships
               (user_id,store_id,business_id,role,capabilities)
               SELECT %s,id,business_id,'manager',ARRAY['reports.manage'] FROM stores WHERE id=%s""",
            (user_id, mobile.stores[0]),
        )
    return user_id, mobile.login("heads-up-manager")


def _heads_up_rows():
    with db_connection() as connection:
        return (
            connection.execute("SELECT count(*) FROM store_heads_up").fetchone()[0],
            connection.execute(
                "SELECT count(*) FROM account_audit WHERE action='heads_up.changed'"
            ).fetchone()[0],
        )


def test_native_manager_crud_and_role_matrix(mobile):
    manager_id, manager = _native_manager(mobile)
    crew = mobile.login("crew")
    owner = mobile.login("owner")
    admin = mobile.login("viewer")
    with db_connection() as connection:
        connection.execute(
            """UPDATE account_store_memberships
               SET capabilities=ARRAY['reports.view','reports.manage','reports.submit']
               WHERE user_id IN (%s,%s)""",
            (mobile.users["owner"], mobile.users["viewer"]),
        )
        connection.execute(
            """UPDATE business_memberships
               SET capabilities=ARRAY['reports.view','reports.manage','reports.submit']
               WHERE user_id=%s""",
            (mobile.users["viewer"],),
        )

    resolved_admin = mobile.accounts.resolve_actor(admin)
    assert {"reports.view", "reports.manage", "reports.submit"} <= set(resolved_admin.capabilities)

    empty = mobile.send("GET", "/api/mobile/heads-up", token=manager)
    assert empty.status_code == 200 and empty.json() == {"message": "", "updatedAt": None}

    created = mobile.send(
        "POST", "/api/mobile/heads-up", token=manager,
        json={"expectedStoreId": mobile.stores[0], "message": "  Delivery\n at   opening.  "},
    )
    assert created.status_code == 200, created.text
    assert created.json()["message"] == "Delivery at opening."
    assert mobile.send("GET", "/api/mobile/heads-up", token=crew).json()["message"] == "Delivery at opening."

    edited = mobile.send(
        "POST", "/api/mobile/heads-up", token=manager,
        json={"expectedStoreId": mobile.stores[0], "message": "Updated handoff."},
    )
    assert edited.status_code == 200 and edited.json()["message"] == "Updated handoff."
    cleared = mobile.send(
        "POST", "/api/mobile/heads-up", token=manager,
        json={"expectedStoreId": mobile.stores[0], "message": " \n\t "},
    )
    assert cleared.status_code == 200 and cleared.json()["message"] == ""

    assert mobile.send(
        "POST", "/api/mobile/heads-up", token=crew,
        json={"expectedStoreId": mobile.stores[0], "message": "Crew write"},
    ).status_code == 403
    for token in (owner, admin):
        assert mobile.send("GET", "/api/mobile/heads-up", token=token).status_code == 403
        assert mobile.send(
            "POST", "/api/mobile/heads-up", token=token,
            json={"expectedStoreId": mobile.stores[0], "message": "Privileged role write"},
        ).status_code == 403

    with db_connection() as connection:
        assert connection.execute(
            "SELECT message FROM store_heads_up WHERE store_id=%s", (mobile.stores[0],)
        ).fetchone() == ("",)
        assert connection.execute(
            """SELECT actor_user_id,store_id,count(*) FROM account_audit
               WHERE action='heads_up.changed' GROUP BY actor_user_id,store_id"""
        ).fetchone() == (manager_id, mobile.stores[0], 3)


def test_native_and_web_share_message_and_reject_store_spoof_and_bad_input(mobile):
    _, manager = _native_manager(mobile)
    crew = mobile.login("crew")
    web_login = mobile.send(
        "POST", "/api/accounts/login",
        json={"storeCode": "mobile-first", "username": "heads-up-manager", "password": mobile.password},
    )
    web_cookie = next(value.split(";", 1)[0] for value in web_login.headers.get_list("set-cookie")
                      if value.startswith("shiftly_account_session="))

    native = mobile.send(
        "POST", "/api/mobile/heads-up", token=manager,
        json={
            "expectedStoreId": mobile.stores[0],
            "storeId": mobile.stores[2],
            "message": "Native handoff.",
        },
    )
    assert native.status_code == 200, native.text
    mobile.client.cookies.clear()
    web_read = mobile.client.get("/api/heads-up", headers={"Cookie": web_cookie})
    assert web_read.status_code == 200 and web_read.json()["message"] == "Native handoff."

    mobile.client.cookies.clear()
    web_write = mobile.client.post(
        "/api/heads-up", headers={"Cookie": web_cookie},
        json={"expectedStoreId": mobile.stores[0], "storeId": mobile.stores[2], "message": "Web handoff."},
    )
    assert web_write.status_code == 200, web_write.text
    assert mobile.send("GET", "/api/mobile/heads-up", token=crew).json()["message"] == "Web handoff."
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO store_heads_up(store_id,message,updated_at) VALUES(%s,'Foreign handoff.',NOW())",
            (mobile.stores[2],),
        )
    scoped = mobile.send(
        "GET", f"/api/mobile/heads-up?storeId={mobile.stores[2]}", token=crew
    )
    assert scoped.status_code == 200 and scoped.json()["message"] == "Web handoff."

    before = _heads_up_rows()
    stale = mobile.send(
        "POST", "/api/mobile/heads-up", token=manager,
        json={"expectedStoreId": mobile.stores[2], "message": "Wrong store"},
    )
    assert stale.status_code == 409 and stale.json()["errorCode"] == "store_context_changed"
    cases = (
        ({"message": "Missing precondition"}, 400),
        ({"expectedStoreId": mobile.stores[0]}, 400),
        ({"expectedStoreId": mobile.stores[0], "message": 7}, 400),
        ({"expectedStoreId": mobile.stores[0], "message": "x" * 1001}, 400),
    )
    for payload, status in cases:
        response = mobile.send("POST", "/api/mobile/heads-up", token=manager, json=payload)
        assert response.status_code == status, (payload, response.text)
    assert _heads_up_rows() == before
    with db_connection() as connection:
        assert connection.execute(
            "SELECT message FROM store_heads_up WHERE store_id=%s", (mobile.stores[2],)
        ).fetchone() == ("Foreign handoff.",)


@pytest.mark.parametrize("change", ["session", "business_owner", "crew"])
def test_native_write_rechecks_session_and_role_inside_transaction(mobile, monkeypatch, change):
    manager_id, manager = _native_manager(mobile)
    original = StoresService.save_heads_up

    def change_authority_then_save(service, *args, **kwargs):
        with db_connection() as connection:
            if change == "session":
                connection.execute(
                    "UPDATE account_sessions SET revoked_at=NOW() WHERE user_id=%s", (manager_id,)
                )
            elif change == "business_owner":
                connection.execute(
                    """INSERT INTO business_memberships(user_id,business_id,role,capabilities)
                       SELECT %s,business_id,'owner',ARRAY['reports.view','reports.manage','reports.submit']
                       FROM stores WHERE id=%s""",
                    (manager_id, mobile.stores[0]),
                )
            else:
                connection.execute(
                    """UPDATE account_store_memberships
                       SET role='crew',capabilities=ARRAY[]::text[] WHERE user_id=%s""",
                    (manager_id,),
                )
        return original(service, *args, **kwargs)

    monkeypatch.setattr(StoresService, "save_heads_up", change_authority_then_save)
    response = mobile.send(
        "POST", "/api/mobile/heads-up", token=manager,
        json={"expectedStoreId": mobile.stores[0], "message": "Must not persist."},
    )
    assert response.status_code in {401, 403}, response.text
    assert _heads_up_rows() == (0, 0)


def test_web_named_role_policy_and_store_precondition(account_http):
    api = account_http
    with db_connection() as connection:
        connection.execute(
            "UPDATE account_store_memberships SET capabilities=ARRAY['reports.manage'] WHERE user_id=%s",
            (api.users["manager"],),
        )
        connection.execute(
            """UPDATE account_store_memberships
               SET capabilities=ARRAY['reports.view','reports.manage','reports.submit']
               WHERE user_id IN (%s,%s)""",
            (api.users["owner"], api.users["minimal"]),
        )
        connection.execute(
            """UPDATE business_memberships
               SET capabilities=ARRAY['reports.view','reports.manage','reports.submit']
               WHERE user_id IN (%s,%s)""",
            (api.users["owner"], api.users["minimal"]),
        )

    for name in ("owner", "minimal"):
        actor = api.accounts.resolve_actor(api.cookies[name].split("=", 1)[1])
        assert {"reports.view", "reports.manage", "reports.submit"} <= set(actor.capabilities)

    saved = api.request(
        "POST", "/api/heads-up", cookie=api.cookies["manager"],
        payload={"expectedStoreId": api.stores[0], "storeId": api.stores[2], "message": "Browser manager."},
    )
    assert saved.status == 200, saved.body
    assert api.request("GET", "/api/heads-up", cookie=api.cookies["manager"]).json()["message"] == "Browser manager."
    assert api.request("GET", "/api/heads-up", cookie=api.cookies["crew"]).json()["message"] == "Browser manager."
    assert api.request("POST", "/api/heads-up", cookie=api.cookies["crew"], payload={"message": "No"}).status == 401
    for name in ("owner", "minimal"):
        assert api.request("GET", "/api/heads-up", cookie=api.cookies[name]).status in {401, 403}
        assert api.request("POST", "/api/heads-up", cookie=api.cookies[name], payload={"message": "No"}).status in {401, 403}

    before = _heads_up_rows()
    stale = api.request(
        "POST", "/api/heads-up", cookie=api.cookies["manager"],
        payload={"expectedStoreId": api.stores[2], "message": "Stale"},
    )
    assert stale.status == 409
    assert _heads_up_rows() == before


def test_production_can_read_heads_up_but_cannot_edit(mobile):
    _, manager = _native_manager(mobile)
    with db_connection() as connection:
        connection.execute("UPDATE account_store_memberships SET role='production',capabilities=ARRAY[]::text[] WHERE user_id=%s",(mobile.users['crew'],))
    token=mobile.login('crew')
    assert mobile.send('POST','/api/mobile/heads-up',token=manager,json={'expectedStoreId':mobile.stores[0],'message':'Production reminder'}).status_code==200
    assert mobile.send('GET','/api/mobile/heads-up',token=token).json()['message']=='Production reminder'
    assert mobile.send('POST','/api/mobile/heads-up',token=token,json={'expectedStoreId':mobile.stores[0],'message':'Overwrite'}).status_code==403
