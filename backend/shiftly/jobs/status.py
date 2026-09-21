"""Worker-owned observations readable by a different API process."""

import logging
import uuid

import psycopg

LOG = logging.getLogger("shiftly.worker")
WORKER_NAME = "briefing"


def unavailable_status(state="unavailable"):
    return {"status": "degraded", "state": state, "running": False,
            "lastPollAgeSeconds": None, "lastCompletionAgeSeconds": None,
            "completedJobs": 0, "consecutiveErrors": 0,
            "lastActivityAgeSeconds": None, "queueDepth": None, "oldestQueuedAgeSeconds": None}


class PersistentWorkerStatus:
    """Only a worker holding the singleton session lock constructs this writer.

    Publication failures do not kill queue processing or refresh a stale reader.
    Each process has a fresh instance ID; updates cannot overwrite a newer writer.
    """

    def __init__(self, connection_factory, *, instance_id=None, ownership_check=None):
        self.connect = connection_factory
        self.instance_id = instance_id if instance_id is not None else uuid.uuid4()
        self.registered = False
        self.ownership_check = ownership_check

    def update(self, phase, *, polled=False, completed=False, errors=0):
        try:
            if self.ownership_check is not None:
                self.ownership_check()
            with self.connect() as connection:
                if not self.registered:
                    connection.execute(
                        """INSERT INTO runtime_worker_status
                           (worker_name, instance_id, state, running, observed_at)
                           VALUES (%s, %s, %s, %s, clock_timestamp())
                           ON CONFLICT (worker_name) DO UPDATE SET
                             instance_id=EXCLUDED.instance_id, state=EXCLUDED.state,
                             running=EXCLUDED.running, observed_at=EXCLUDED.observed_at,
                             last_poll_at=NULL, last_completion_at=NULL,
                             completed_jobs=0, consecutive_errors=0""",
                        (WORKER_NAME, self.instance_id, phase, phase != "stopped"),
                    )
                connection.execute(
                    """UPDATE runtime_worker_status SET state=%s, running=%s,
                       observed_at=clock_timestamp(),
                       last_poll_at=CASE WHEN %s THEN clock_timestamp() ELSE last_poll_at END,
                       last_completion_at=CASE WHEN %s THEN clock_timestamp() ELSE last_completion_at END,
                       completed_jobs=completed_jobs + %s, consecutive_errors=%s
                       WHERE worker_name=%s AND instance_id=%s""",
                    (phase, phase != "stopped", polled, completed, int(bool(completed)),
                     errors, WORKER_NAME, self.instance_id),
                )
                connection.commit()
            self.registered = True
        except (RuntimeError, psycopg.Error):
            LOG.warning('{"event":"worker_observation_failed","errorCode":"database_unavailable"}')


class DatabaseWorkerStatus:
    def __init__(self, connection_factory, *, stale_seconds=60):
        self.connect = connection_factory
        self.stale_seconds = stale_seconds

    def __call__(self):
        return self.snapshot()

    def snapshot(self):
        try:
            with self.connect() as connection:
                row = connection.execute(
                    """SELECT state, running, completed_jobs, consecutive_errors,
                       EXTRACT(EPOCH FROM clock_timestamp()-observed_at),
                       EXTRACT(EPOCH FROM clock_timestamp()-last_poll_at),
                       EXTRACT(EPOCH FROM clock_timestamp()-last_completion_at)
                       FROM runtime_worker_status WHERE worker_name=%s""", (WORKER_NAME,),
                ).fetchone()
                queue = connection.execute(
                    """SELECT count(*), EXTRACT(EPOCH FROM clock_timestamp()-min(j.created_at))
                       FROM briefing_jobs j LEFT JOIN briefing_job_recovery r ON r.job_id=j.id
                       WHERE NOT COALESCE(r.terminal, FALSE)
                         AND (j.status='processing' OR
                           (j.status IN ('pending','failed') AND j.attempts < 3))""",
                ).fetchone()
        except (RuntimeError, psycopg.Error):
            return unavailable_status()
        def age(value):
            return round(max(0.0, float(value)), 3) if value is not None else None
        result = unavailable_status("not_started")
        result.update(queueDepth=queue[0], oldestQueuedAgeSeconds=age(queue[1]))
        if row is None:
            return result
        phase, running, completed, errors, activity_age, poll_age, completion_age = row
        stale = float(activity_age) >= self.stale_seconds
        healthy = running and poll_age is not None and not stale and phase in {"idle", "processing"}
        result.update(status="ok" if healthy else "degraded",
                      state="stalled" if running and stale else phase, running=running,
                      lastActivityAgeSeconds=age(activity_age), lastPollAgeSeconds=age(poll_age),
                      lastCompletionAgeSeconds=age(completion_age), completedJobs=completed,
                      consecutiveErrors=errors)
        return result
