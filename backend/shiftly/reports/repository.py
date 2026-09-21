"""PostgreSQL report access using a caller-supplied connection factory.

Connections must be dedicated, closing context managers (the existing psycopg
connection contract). In particular a weekly connection's close releases its
session advisory lock. No credentials, settings or global clients live here.
"""

import uuid
from contextlib import contextmanager

from .errors import WeeklyOverviewBusy


class ReportsRepository:
    def __init__(self, connect):
        self.connect = connect

    def enqueue(self, employee, shift, notes, store_id, report_hash):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO reports (id, store_id, employee, shift, notes, report_hash)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (store_id, report_hash) DO NOTHING
                    RETURNING id, created_at
                    """,
                    (str(uuid.uuid4()), store_id, employee, shift, notes, report_hash),
                )
                saved = cursor.fetchone()
                if saved is None:
                    raise ValueError("This report matches a previous submission and was not sent again.")
                cursor.execute("INSERT INTO briefing_jobs (report_id) VALUES (%s)", (saved[0],))
            connection.commit()
        return saved

    def latest_for_employee(self, store_id, employee):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT notes, created_at
                    FROM reports
                    WHERE store_id = %s AND lower(employee) = lower(%s)
                    ORDER BY created_at DESC
                    LIMIT 1
                    """, (store_id, employee),
                )
                return cursor.fetchone()

    def for_manager(self, manager_id):
        # Report inbox remains membership-wide, not selected-store-only.
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.id, r.employee, r.shift, r.notes, r.created_at,
                           j.status, j.last_error, b.summary, b.wins, b.risks, b.follow_up
                    FROM reports r
                    JOIN briefing_jobs j ON j.report_id = r.id
                    LEFT JOIN briefings b ON b.report_id = r.id
                    JOIN store_memberships sm ON sm.store_id = r.store_id AND sm.manager_user_id = %s
                    ORDER BY r.created_at DESC
                    """, (manager_id,),
                )
                return cursor.fetchall()

    @contextmanager
    def weekly_session(self, store_id):
        with self.connect() as connection:
            # Keep the provider call outside a transaction while retaining the
            # dedicated session's nonblocking, per-store advisory lock.
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (f"shiftly:weekly:{store_id}",))
                if not cursor.fetchone()[0]:
                    raise WeeklyOverviewBusy("Weekly overview is being prepared. Try again shortly.")
                yield WeeklyReportSession(cursor, store_id)


class WeeklyReportSession:
    """Store-bound queries valid only within ReportsRepository.weekly_session."""

    def __init__(self, cursor, store_id):
        self.cursor = cursor
        self.store_id = store_id

    def source_rows(self, limit):
        self.cursor.execute(
            """
            SELECT employee, shift, notes, created_at, id, COUNT(*) OVER()
            FROM reports
            WHERE store_id = %s AND created_at >= NOW() - INTERVAL '7 days'
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """, (self.store_id, limit),
        )
        return self.cursor.fetchall()

    def cached_result(self, fingerprint):
        self.cursor.execute(
            """
            SELECT summary, wins, risks, follow_up
            FROM weekly_overview_cache
            WHERE store_id = %s AND source_fingerprint = %s
            """, (self.store_id, fingerprint),
        )
        return self.cursor.fetchone()

    def save_result(self, fingerprint, report_count, result):
        self.cursor.execute(
            """
            INSERT INTO weekly_overview_cache
                (store_id, source_fingerprint, report_count, summary, wins, risks, follow_up)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (store_id) DO UPDATE SET
                source_fingerprint = EXCLUDED.source_fingerprint,
                report_count = EXCLUDED.report_count,
                summary = EXCLUDED.summary,
                wins = EXCLUDED.wins,
                risks = EXCLUDED.risks,
                follow_up = EXCLUDED.follow_up,
                generated_at = NOW()
            """,
            (self.store_id, fingerprint, report_count, result["summary"], result["wins"], result["risks"], result["follow_up"]),
        )
