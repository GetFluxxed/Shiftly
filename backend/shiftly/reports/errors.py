"""Domain outcomes translated to HTTP only by the calling adapter."""


class ReportRejected(Exception):
    """The quality gate declined a report before anything was persisted."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class WeeklyOverviewBusy(RuntimeError):
    """Generation is already in progress or the process is at capacity."""
