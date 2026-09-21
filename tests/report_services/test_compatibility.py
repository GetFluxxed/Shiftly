"""Legacy adapters retain their injection points and response behavior."""

import io
import json
import uuid
from datetime import datetime, timezone
from threading import BoundedSemaphore, Event

import pytest

import reporting
import routes
import server
from backend.shiftly.reports import ReportSubmission, WeeklyOverviewBusy


STAMP = datetime(2026, 9, 21, tzinfo=timezone.utc)
FIELDS = {"employee": "Nina", "shift": "closing", "notes": "Restocked the freezer."}


class Handler:
    path = "/api/reports"
    client_address = ("127.0.0.1", 9999)

    def __init__(self, raw=None):
        body = json.dumps(FIELDS).encode() if raw is None else raw
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.response = None

    def send_json(self, status, body):
        assert self.response is None
        self.response = status, body


def no_server_lookup():
    pytest.fail("Report submission must not discover dependencies by importing server")


def test_server_adapter_uses_current_replacement_points(monkeypatch):
    monkeypatch.setattr(routes, "_server_module", no_server_lookup)
    calls = []
    monkeypatch.setattr(server, "is_crew", lambda handler: "selected-store")
    monkeypatch.setattr(server, "ensure_submission_allowed", lambda *args: calls.append(("policy", args)))
    monkeypatch.setattr(server, "validate_report", lambda report: {"status": "accepted"})
    def enqueue(*args):
        calls.append(("enqueue", args))
        return uuid.UUID(int=1), STAMP
    monkeypatch.setattr(server, "queue_report", enqueue)
    handler = Handler()
    server.ShiftlyHandler.submit_report(handler)
    assert handler.response == (202, {"date": STAMP.isoformat(), "status": "pending"})
    assert calls == [("policy", ("selected-store", "Nina", "Restocked the freezer.")), ("enqueue", ("Nina", "closing", "Restocked the freezer.", "selected-store"))]


def test_direct_route_caller_still_works_without_server_lookup(monkeypatch):
    monkeypatch.setattr(routes, "_server_module", no_server_lookup)
    monkeypatch.setattr(routes, "is_crew", lambda handler: "selected-store")
    monkeypatch.setattr(reporting, "ensure_submission_allowed", lambda *args: None)
    monkeypatch.setattr(reporting, "validate_report", lambda report: {"status": "accepted"})
    monkeypatch.setattr(reporting, "queue_report", lambda *args: (uuid.UUID(int=1), STAMP))
    handler = Handler()
    routes.submit_report(handler)
    assert handler.response[0] == 202


@pytest.mark.parametrize("failure,expected", [
    (ValueError("policy denied"), (400, {"error": "policy denied"})),
    (RuntimeError("provider unavailable"), (503, {"error": "provider unavailable"})),
    (None, (422, {"error": "More detail needed"})),
])
def test_injected_domain_outcomes_keep_http_mapping(failure, expected):
    def quality(report):
        if failure:
            raise failure
        return {"status": "rejected", "reason": "More detail needed"}
    submission = ReportSubmission(ensure_allowed=lambda *args: None, quality_gate=quality, enqueue=lambda *args: pytest.fail("Must not enqueue"))
    handler = Handler()
    routes.submit_report(handler, submission=submission, resolve_store=lambda handler: "alpha")
    assert handler.response == expected


def test_authorization_and_admission_precede_body_parsing_and_services(monkeypatch):
    class UnexpectedSubmission:
        def submit(self, *args):
            pytest.fail("Must not enter the service")
    denied = Handler(b"invalid JSON")
    routes.submit_report(denied, submission=UnexpectedSubmission(), resolve_store=lambda handler: None)
    assert denied.response == (401, {"error": "Crew sign-in required."})
    monkeypatch.setattr(routes, "rate_limited", lambda handler: True)
    throttled = Handler(b"invalid JSON")
    routes.submit_report(throttled, submission=UnexpectedSubmission(), resolve_store=lambda handler: "alpha")
    assert throttled.response == (429, {"error": "Too many submissions. Try again later."})


def test_reporting_wrappers_resolve_latest_factory_clock_settings_and_wake(monkeypatch, isolated_database):
    from database import db_connection
    with db_connection() as connection:
        store = connection.execute("INSERT INTO stores (name, access_code_hash) VALUES ('Alpha', %s) RETURNING id", ("f" * 64,)).fetchone()[0]
    wake = Event()
    connections = []
    def connect():
        connections.append(True)
        return db_connection()
    monkeypatch.setattr(reporting, "db_connection", connect)
    monkeypatch.setattr(reporting, "JOB_WAKE", wake)
    _, created = reporting.queue_report("Nina", "closing", "Original notes", store)
    assert wake.is_set() and len(connections) == 1
    monkeypatch.setattr(reporting, "REPORT_COOLDOWN_SECONDS", 100)
    monkeypatch.setattr(reporting.time, "time", lambda: created.timestamp() + 20)
    with pytest.raises(ValueError, match="Please wait 80 seconds"):
        reporting.ensure_submission_allowed(store, "Nina", "New notes")
    assert len(connections) == 2


def test_weekly_wrapper_resolves_replaced_capacity_before_any_io(monkeypatch):
    capacity = BoundedSemaphore(1)
    capacity.acquire()
    monkeypatch.setattr(reporting, "WEEKLY_GENERATION_SLOTS", capacity)
    monkeypatch.setattr(reporting, "db_connection", lambda: pytest.fail("No connection at capacity"))
    try:
        with pytest.raises(WeeklyOverviewBusy):
            reporting.weekly_overview("alpha")
    finally:
        capacity.release()
