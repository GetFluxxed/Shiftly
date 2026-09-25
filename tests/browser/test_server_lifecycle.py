"""Browser teardown must finish database work before releasing its fixture."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from http.server import BaseHTTPRequestHandler
from threading import Event, Thread

import pytest

from database import db_connection
from tests.browser.conftest import BrowserApi, BrowserHTTPServer


def test_server_close_waits_for_inflight_database_request(isolated_database):
    querying = Event()
    finish_query = Event()
    listener_stopped = Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with db_connection() as connection:
                connection.execute("SELECT COUNT(*) FROM account_users").fetchone()
                querying.set()
                if not finish_query.wait(timeout=10):
                    raise RuntimeError("The test did not release the pending query.")
                connection.execute("SELECT COUNT(*) FROM businesses").fetchone()
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = BrowserHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()

    def close_server():
        httpd.shutdown()
        listener_stopped.set()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(BrowserApi(f"http://127.0.0.1:{httpd.server_address[1]}").request, "GET", "/")
        closing = None
        try:
            assert querying.wait(timeout=5)
            closing = pool.submit(close_server)
            assert listener_stopped.wait(timeout=5)
            # Stopping the listener alone must not release the database fixture.
            with pytest.raises(TimeoutError):
                closing.result(timeout=0.1)
        finally:
            finish_query.set()
            if closing is None:
                close_server()
            else:
                closing.result(timeout=5)
        assert pending.result(timeout=5).status == 204
