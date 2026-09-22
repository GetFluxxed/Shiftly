"""Report workflows using trusted actor/store IDs and explicit dependencies.

HTTP adapters own authentication, request parsing and admission limits. These
services never take store/manager authority from submitted report fields.
"""

import hashlib
import re
from difflib import SequenceMatcher

from .errors import ReportRejected


def normalized_notes(notes):
    return re.sub(r"\s+", " ", notes.casefold()).strip()


def prepare_report(fields):
    """Preserve the legacy normalization, limits and validation order."""
    def clean(value, limit):
        return re.sub(r"\s+", " ", value or "").strip()[:limit]

    employee = clean(fields.get("employee"), 80)
    shift = clean(fields.get("shift"), 20)
    notes = clean(fields.get("notes"), 2000)
    if not employee or not notes:
        raise ValueError("Enter your name and meaningful shift notes.")
    if shift not in {"opening", "midday", "closing", "other"}:
        raise ValueError("Choose a valid shift.")
    return {"employee": employee, "shift": shift, "notes": notes}


class ReportSubmission:
    """Validate, apply policy, consult quality, then enqueue exactly once.

    Dependencies are callables: ensure_allowed(store_id, employee, notes),
    quality_gate(report), and enqueue(employee, shift, notes, store_id). This
    also lets the legacy adapter retain its replaceable public functions.
    """

    def __init__(self, *, ensure_allowed, quality_gate, enqueue):
        self.ensure_allowed = ensure_allowed
        self.quality_gate = quality_gate
        self.enqueue = enqueue

    def submit(self, store_id, fields, *, actor_token=None, accounts=None, legacy_credentials=None):
        report = prepare_report(fields)
        employee, shift, notes = report["employee"], report["shift"], report["notes"]
        self.ensure_allowed(store_id, employee, notes)
        quality = self.quality_gate(report)
        if quality.get("status") != "accepted":
            raise ReportRejected(quality.get("reason") or "Please add meaningful shift details and try again.")
        if actor_token is not None or legacy_credentials is not None:
            return self.enqueue(employee, shift, notes, store_id, actor_token=actor_token, accounts=accounts,
                                legacy_credentials=legacy_credentials)
        return self.enqueue(employee, shift, notes, store_id)


class ReportsService:
    """Report policy, persistence orchestration and manager-facing results.

    The repository exposes latest_for_employee, enqueue and for_manager. The
    wake callback is invoked only after the repository commits the report/job.
    clock returns Unix seconds; IDs must come from the authorization boundary.
    """

    def __init__(self, repository, *, cooldown_seconds, similarity_threshold, clock, wake):
        self.repository = repository
        self.cooldown_seconds = cooldown_seconds
        self.similarity_threshold = similarity_threshold
        self.clock = clock
        self.wake = wake

    def ensure_submission_allowed(self, store_id, employee, notes):
        previous = self.repository.latest_for_employee(store_id, employee)
        if not previous:
            return
        previous_notes, created_at = previous
        seconds_since_previous = self.clock() - created_at.timestamp()
        if seconds_since_previous < self.cooldown_seconds:
            remaining = max(1, int(self.cooldown_seconds - seconds_since_previous))
            raise ValueError(f"Please wait {remaining} seconds before sending another report.")
        similarity = SequenceMatcher(None, normalized_notes(previous_notes), normalized_notes(notes)).ratio()
        if similarity >= self.similarity_threshold:
            raise ValueError("This report is too similar to your previous report. Add the new details from this shift and try again.")

    def queue_report(self, employee, shift, notes, store_id, *, actor_token=None, accounts=None, legacy_credentials=None):
        # Keep the historical hash bytes and store-scoped uniqueness contract.
        report_hash = hashlib.sha256(f"{employee.lower()}|{shift}|{notes.lower()}".encode()).hexdigest()
        if actor_token is not None or legacy_credentials is not None:
            saved = self.repository.enqueue(employee, shift, notes, store_id, report_hash,
                                            actor_token=actor_token, accounts=accounts,
                                            legacy_credentials=legacy_credentials)
        else:
            saved = self.repository.enqueue(employee, shift, notes, store_id, report_hash)
        self.wake()
        return saved

    def list_for_manager(self, manager_id):
        rows = self.repository.for_manager(manager_id)
        return self._results(rows)

    def list_for_actor(self, token, accounts):
        return self._results(self.repository.for_actor(token, accounts))

    @staticmethod
    def _results(rows):
        return [
            {
                "id": str(row[0]),
                "employee": row[1],
                "shift": row[2],
                "notes": row[3],
                "date": row[4].isoformat(),
                "status": row[5],
                "error": row[6],
                "briefing": {
                    "summary": row[7],
                    "wins": row[8] or [],
                    "risks": row[9] or [],
                    "follow_up": row[10],
                } if row[8] is not None else None,
            }
            for row in rows
        ]
