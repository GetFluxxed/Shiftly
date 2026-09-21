"""Bounded weekly generation and caching, independent of HTTP and provider I/O."""

import hashlib
import json

from .errors import WeeklyOverviewBusy


def weekly_source(rows, report_count, *, model, prompt, max_reports, max_input_chars):
    def encoded(value):
        return json.dumps(value, ensure_ascii=False).encode("utf-8")

    fingerprint = hashlib.sha256(encoded(["weekly-v2", model, prompt, max_reports, max_input_chars, report_count]))
    notes = []
    input_length = 0
    for employee, shift, report_notes, created_at, report_id in rows:
        entry = f"Employee: {employee}\nShift: {shift}\nDate: {created_at.strftime('%Y-%m-%d')}\nNotes: {report_notes}"
        separator_length = 2 if notes else 0
        remaining = max_input_chars - input_length - separator_length
        if len(entry) > remaining:
            break
        fingerprint.update(encoded([str(report_id), employee, shift, created_at.isoformat(), report_notes]))
        notes.append(entry)
        input_length += separator_length + len(entry)
    return fingerprint.hexdigest(), "\n\n".join(notes), len(notes)


def validated_weekly_result(result):
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("summary"), str)
        or not result["summary"].strip()
        or not isinstance(result.get("follow_up"), str)
        or any(
            not isinstance(result.get(key), list)
            or any(not isinstance(item, str) for item in result[key])
            for key in ("wins", "risks")
        )
    ):
        raise RuntimeError("Weekly overview returned an invalid response.")
    return {
        "summary": result["summary"].strip()[:4000],
        "wins": [item.strip()[:500] for item in result["wins"][:20] if item.strip()],
        "risks": [item.strip()[:500] for item in result["risks"][:20] if item.strip()],
        "follow_up": result["follow_up"].strip()[:4000],
    }


def weekly_cache_result(row):
    return validated_weekly_result({
        "summary": row[0], "wins": row[1], "risks": row[2], "follow_up": row[3],
    })


class WeeklyOverviewService:
    """The caller shares one capacity gate across instances in its process.

    repository.weekly_session(store_id) yields a store-bound source/cache session.
    provider(report, prompt) returns structured output; it owns the transport.
    """

    def __init__(self, repository, *, provider, capacity, model, prompt, max_reports, max_input_chars):
        self.repository = repository
        self.provider = provider
        self.capacity = capacity
        self.model = model
        self.prompt = prompt
        self.max_reports = max_reports
        self.max_input_chars = max_input_chars

    def overview(self, store_id):
        # Refuse before opening a connection when generation is at capacity.
        if not self.capacity.acquire(blocking=False):
            raise WeeklyOverviewBusy("Weekly overview is being prepared. Try again shortly.")
        try:
            return self._generate(store_id)
        finally:
            self.capacity.release()

    def _generate(self, store_id):
        with self.repository.weekly_session(store_id) as session:
            rows = session.source_rows(self.max_reports)
            report_count = rows[0][5] if rows else 0
            if not rows:
                return {"summary": "No shift reports have been submitted in the last seven days.", "reportCount": 0, "includedReportCount": 0, "truncated": False}
            fingerprint, notes, included_count = weekly_source(
                [(employee, shift, report_notes, created_at, report_id) for employee, shift, report_notes, created_at, report_id, _ in rows],
                report_count, model=self.model, prompt=self.prompt,
                max_reports=self.max_reports, max_input_chars=self.max_input_chars,
            )
            coverage = {"reportCount": report_count, "includedReportCount": included_count, "truncated": included_count < report_count}
            if not included_count:
                raise RuntimeError("The latest report is too large for a weekly overview. Review it in the inbox.")
            cached = session.cached_result(fingerprint)
            if cached:
                try:
                    result = weekly_cache_result(cached)
                except RuntimeError:
                    pass  # Replace invalid entries left by an earlier version.
                else:
                    return {**result, **coverage}
            result = validated_weekly_result(self.provider(
                {"employee": "store team", "shift": "weekly overview", "notes": notes}, self.prompt,
            ))
            session.save_result(fingerprint, report_count, result)
            return {**result, **coverage}
