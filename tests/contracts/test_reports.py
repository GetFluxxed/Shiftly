from database import db_connection
from reporting import queue_report


def test_report_submission_returns_pending_contract(api, workspace):
    crew_login = api.request(
        "POST",
        "/api/auth/login",
        payload={"storeCode": workspace["store_code"], "role": "crew", "password": workspace["crew_password"]},
    )
    crew_cookie = crew_login.cookies()[0]
    submitted = api.request(
        "POST",
        "/api/reports",
        cookie=crew_cookie,
        payload={"employee": "Crew Member", "shift": "closing", "notes": "Counted the freezer and logged the delivery."},
    )
    assert submitted.status == 202
    assert set(submitted.json()) >= {"date", "status"}
    assert submitted.json()["status"] == "pending"

    malformed = api.request("POST", "/api/reports", cookie=crew_cookie, raw=b"[]")
    assert malformed.status == 400


def test_heads_up_is_store_scoped_for_crew_and_manager(api, workspace):
    saved = api.request(
        "POST",
        "/api/heads-up",
        cookie=workspace["manager_cookie"],
        payload={"message": "Deliveries arrive before close."},
    )
    assert saved.status == 200
    assert saved.json()["message"] == "Deliveries arrive before close."

    crew_login = api.request(
        "POST",
        "/api/auth/login",
        payload={"storeCode": workspace["store_code"], "role": "crew", "password": workspace["crew_password"]},
    )
    visible = api.request("GET", "/api/heads-up", cookie=crew_login.cookies()[0])
    assert visible.status == 200
    assert visible.json()["message"] == "Deliveries arrive before close."


def test_weekly_pending_then_ready_and_dependency_failure(api, workspace, monkeypatch):
    queue_report("Weekly Crew", "closing", "A valid weekly shift update.", workspace["store_id"])
    lock = db_connection()
    lock.autocommit = True
    lock.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (f"shiftly:weekly:{workspace['store_id']}",))
    try:
        pending = api.request("GET", "/api/weekly-overview", cookie=workspace["manager_cookie"])
        assert pending.status == 202
        assert pending.json()["status"] == "pending"
        assert pending.json()["retryAfter"] > 0
    finally:
        lock.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (f"shiftly:weekly:{workspace['store_id']}",))
        lock.close()

    ready = api.request("GET", "/api/weekly-overview", cookie=workspace["manager_cookie"])
    assert ready.status == 200
    assert set(ready.json()) >= {"summary", "wins", "risks", "follow_up", "reportCount"}

    monkeypatch.setattr("reporting.call_openai", lambda *args: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    with db_connection() as connection:
        connection.execute("DELETE FROM weekly_overview_cache WHERE store_id = %s", (workspace["store_id"],))
        connection.execute(
            "UPDATE reports SET notes = notes || ' changed' WHERE store_id = %s",
            (workspace["store_id"],),
        )
    failed = api.request("GET", "/api/weekly-overview", cookie=workspace["manager_cookie"])
    assert failed.status == 503
    assert "provider unavailable" in failed.json()["error"]
