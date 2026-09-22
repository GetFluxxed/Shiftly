"""Separate supervised worker: python -m backend.shiftly.jobs.worker.

The command reads explicit environment settings, refuses an unmigrated schema,
and never starts a web listener. Tests may call run_worker with a fake provider.
"""

import logging
import signal
from functools import partial
from threading import Event, Thread

import psycopg

from backend.shiftly.runtime.database import DatabaseResources
from backend.shiftly.runtime.migrate import require_schema
from backend.shiftly.runtime.provider import make_provider
from .status import PersistentWorkerStatus


class ShutdownWake:
    """No shared-memory web event is needed: poll the durable queue, stop promptly."""
    def __init__(self, stop):
        self.stop = stop

    def wait(self, timeout):
        return self.stop.wait(timeout)

    def clear(self):
        pass


def run_worker(settings, *, provider=None, stop_event=None, install_signals=False):
    # Imports stay inside explicit runtime execution, never package construction.
    import reporting
    stop = stop_event if stop_event is not None else Event()
    provider = provider if provider is not None else make_provider(settings)
    old_signals = {}
    if install_signals:
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_signals[signum] = signal.signal(signum, lambda *_: stop.set())
    try:
        with DatabaseResources(settings) as resources:
            require_schema(resources.connection)
            # A dedicated session holds the singleton lock for this worker's life.
            with resources.weekly_connection() as ownership:
                ownership.autocommit = True
                locked = ownership.execute(
                    "SELECT pg_try_advisory_lock(hashtext(current_database()), hashtext(current_schema() || ':shiftly-briefing-worker'))",
                ).fetchone()[0]
                if not locked:
                    raise RuntimeError("A separate briefing worker is already running.")
                ownership_lost = Event()
                def check_ownership():
                    try:
                        ownership.execute("SELECT 1")
                    except psycopg.Error:
                        ownership_lost.set()
                        stop.set()
                        raise
                def claim():
                    # A disconnected ownership session cannot keep polling jobs.
                    check_ownership()
                    return reporting.claim_job(connect=resources.connection)
                status = PersistentWorkerStatus(
                    resources.connection, ownership_check=check_ownership,
                )
                failures = []
                def loop():
                    try:
                        reporting.worker_loop(
                            stop_event=stop, claim=claim,
                            load_report=partial(reporting.job_report, connect=resources.connection),
                            provider=provider,
                            complete=partial(reporting.complete_job, connect=resources.connection,
                                             model=settings.openai_model),
                            fail=partial(reporting.fail_job, connect=resources.connection),
                            status=status, wake=ShutdownWake(stop),
                        )
                    except BaseException as error:
                        failures.append(error)
                thread = Thread(target=loop, name="briefing-worker", daemon=True)
                thread.start()
                while thread.is_alive() and not stop.is_set():
                    thread.join(timeout=0.1)
                if stop.is_set():
                    thread.join(timeout=settings.shutdown_timeout)
                if thread.is_alive():
                    # Main returns to its supervisor without waiting for stuck AI;
                    # the durable claim stays fenced and expires normally.
                    raise RuntimeError("Worker shutdown deadline exceeded; unfinished work remains recoverable.")
                if failures:
                    raise RuntimeError("Worker stopped unexpectedly; inspect sanitized diagnostics.") from None
                if ownership_lost.is_set():
                    raise RuntimeError("Worker ownership was lost; restart under the process supervisor.")
    finally:
        for signum, previous in old_signals.items():
            signal.signal(signum, previous)


def main():
    from config import load_settings
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        run_worker(load_settings(load_env=False), install_signals=True)
    except (RuntimeError, ValueError, psycopg.Error):
        raise SystemExit("Worker stopped; check configuration, schema readiness and sanitized diagnostics.") from None


if __name__ == "__main__":
    main()
