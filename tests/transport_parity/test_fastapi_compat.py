def test_fastapi_auth_cookie_status_logout_and_crew_login(transport_clients):
    fastapi_client, _ = transport_clients
    from tests.account_fixtures import seed_workspace
    seed_workspace(store_code='fastapi-store',manager_name='fastapi-manager')
    signup=fastapi_client.post('/api/accounts/login',json={'username':'fastapi-manager','password':'manager-password-123'})
    assert signup.status_code==200
    assert signup.json()["role"] == "manager"
    assert fastapi_client.get("/api/auth/status").json()["role"] == "manager"

    logout = fastapi_client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert fastapi_client.get("/api/auth/status").json()["authenticated"] is False

    login = fastapi_client.post(
        "/api/auth/login",
        json={"username": "fastapi-manager-crew", "password": "crew-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "crew"
    assert fastapi_client.get("/api/auth/status").json()["role"] == "crew"


def test_fastapi_reports_heads_up_managers_and_weekly_contract(transport_clients):
    fastapi_client, _ = transport_clients
    from tests.account_fixtures import seed_workspace
    seed_workspace(store_code='operations-store',manager_name='operations-manager')
    signup=fastapi_client.post('/api/accounts/login',json={'username':'operations-manager','password':'manager-password-123'})
    assert signup.status_code==200
    fastapi_client.post("/api/auth/logout")

    crew = fastapi_client.post(
        "/api/auth/login",
        json={"username": "operations-manager-crew", "password": "crew-password-123"},
    )
    assert crew.status_code == 200
    report = fastapi_client.post(
        "/api/reports",
        json={"employee": "Crew", "shift": "closing", "notes": "Completed the closing checklist."},
    )
    assert report.status_code == 202
    assert report.json()["status"] == "pending"
    assert fastapi_client.get("/api/heads-up").status_code == 200
    fastapi_client.post("/api/auth/logout")

    manager = fastapi_client.post(
        "/api/auth/login",
        json={"username": "operations-manager", "password": "manager-password-123"},
    )
    assert manager.status_code == 200
    saved = fastapi_client.post("/api/heads-up", json={"message": "Delivery before close."})
    assert saved.status_code == 200
    assert saved.json()["message"] == "Delivery before close."
    reports = fastapi_client.get("/api/reports")
    assert reports.status_code == 200
    assert reports.json()["reports"][0]["employee"] == "Crew"
    managers = fastapi_client.get("/api/managers")
    assert managers.status_code == 200
    assert managers.json()["managers"][0]["name"] == "operations-manager"
    weekly = fastapi_client.get("/api/weekly-overview")
    assert weekly.status_code == 200
    assert weekly.json()["summary"] == "Weekly ready."


def test_fastapi_auth_and_manager_routes_require_authority(transport_clients):
    fastapi_client, _ = transport_clients
    assert fastapi_client.get("/api/reports").status_code == 401
    assert fastapi_client.post("/api/heads-up", json={"message": "No access"}).status_code == 401
    assert fastapi_client.get("/api/managers").status_code == 401
    assert fastapi_client.get("/api/weekly-overview").status_code == 401
