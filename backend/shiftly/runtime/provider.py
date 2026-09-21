"""Bind explicit settings to the existing provider transport, with no eager I/O."""

from .prompts import SYSTEM_PROMPT


def make_provider(settings):
    def provider(report, prompt=SYSTEM_PROMPT):
        import reporting
        return reporting.call_openai(report, prompt, api_key=settings.openai_api_key,
                                     model=settings.openai_model)
    return provider
