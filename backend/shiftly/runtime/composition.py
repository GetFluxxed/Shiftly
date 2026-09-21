"""Framework-free composition. Construction owns no sockets, threads or DB work."""

import time
from dataclasses import dataclass
from threading import BoundedSemaphore

from backend.shiftly.identity import AdmissionControl, IdentityRepository, IdentityService
from backend.shiftly.reports import ReportSubmission, ReportsRepository, ReportsService, WeeklyOverviewService
from backend.shiftly.stores import StoresRepository, StoresService
from .prompts import QUALITY_PROMPT, WEEKLY_PROMPT


@dataclass(frozen=True)
class Services:
    identity: IdentityService
    stores: StoresService
    reports: ReportsService
    submission: ReportSubmission
    weekly: WeeklyOverviewService
    admission: AdmissionControl


def build_services(*, settings, connection_factory, provider, weekly_connection_factory=None,
                   admission=None, clock=None, wake=None, weekly_capacity=None, session_ttl=28800):
    """Build once per API process; adapters own body/cookie/status translation.

    provider(report, prompt) returns the existing structured AI result.
    Connection factories yield closing transactions; weekly must close sessions.
    wake() is optional because independently running workers poll the durable queue.
    """
    clock = clock if clock is not None else time.time
    admission = admission if admission is not None else AdmissionControl(clock=clock)
    stores = StoresService(StoresRepository(connection_factory))
    identity = IdentityService(IdentityRepository(connection_factory), stores,
                               admin_key=settings.admin_signup_key, session_ttl=session_ttl,
                               admission=admission)
    reports = ReportsService(ReportsRepository(connection_factory),
                             cooldown_seconds=settings.report_cooldown_seconds,
                             similarity_threshold=0.75, clock=clock,
                             wake=wake if wake is not None else lambda: None)
    submission = ReportSubmission(ensure_allowed=reports.ensure_submission_allowed,
                                  quality_gate=lambda report: provider(report, QUALITY_PROMPT),
                                  enqueue=reports.queue_report)
    weekly_connect = weekly_connection_factory if weekly_connection_factory is not None else connection_factory
    weekly = WeeklyOverviewService(ReportsRepository(weekly_connect), provider=provider,
                                    capacity=weekly_capacity if weekly_capacity is not None else BoundedSemaphore(2),
                                    model=settings.openai_model, prompt=WEEKLY_PROMPT,
                                    max_reports=50, max_input_chars=20_000)
    return Services(identity, stores, reports, submission, weekly, admission)
