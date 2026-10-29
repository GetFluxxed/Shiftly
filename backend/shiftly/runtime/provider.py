"""OpenAI transport and explicit runtime binding, with no eager I/O."""

import json
import os
import ssl
import urllib.error
import urllib.request

from .prompts import SYSTEM_PROMPT

try:
    import certifi
except ImportError:
    certifi = None


class ProviderConfigurationError(RuntimeError):
    """A provider request cannot run with the configured inputs."""


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def call_openai(report, system_prompt=SYSTEM_PROMPT, *, api_key=None, model=None):
    api_key = os.environ.get("OPENAI_API_KEY") if api_key is None else api_key
    if not api_key:
        raise ProviderConfigurationError("OPENAI_API_KEY is not configured on the server.")
    content = [{
        "type": "input_text",
        "text": f"Employee: {report['employee']}\nShift: {report['shift']}\nNotes: {report['notes']}",
    }]
    request = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": content},
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": 500,
    }
    http_request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json_bytes(request),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
        with urllib.request.urlopen(http_request, timeout=30, context=ssl_context) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"OpenAI request failed ({error.code}).") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach OpenAI: {error.reason}") from error
    output = payload.get("output", [])
    text = "".join(
        item.get("text", "")
        for message in output if message.get("type") == "message"
        for item in message.get("content", []) if item.get("type") == "output_text"
    )
    if not text:
        raise RuntimeError("OpenAI returned no briefing.")
    return json.loads(text)


def make_provider(settings):
    def provider(report, prompt=SYSTEM_PROMPT):
        return call_openai(
            report, prompt, api_key=settings.openai_api_key, model=settings.openai_model,
        )
    return provider
