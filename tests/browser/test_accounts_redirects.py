import json
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(process.argv[1], 'utf8');
const responseKind = process.argv[2];
const elements = new Map();
const windowListeners = new Map();
const documentListeners = new Map();
const redirects = [];
let fetches = 0;

function element(selector) {
  if (elements.has(selector)) return elements.get(selector);
  const listeners = new Map();
  const value = {
    id: selector.startsWith('#') ? selector.slice(1) : '',
    value: selector === '#invitation-code' ? 'private invitation token' : '',
    textContent: selector === '#team-list' ? 'private roster' : '',
    innerHTML: '',
    checked: false,
    disabled: false,
    dataset: {},
    href: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(type, handler) { listeners.set(type, handler); },
    replaceChildren() { this.textContent = ''; this.innerHTML = ''; },
    reset() { this.value = ''; },
    focus() {},
    after() {},
    closest() { return null; },
    dispatch(type, event = {}) { return listeners.get(type)?.(event); },
  };
  elements.set(selector, value);
  return value;
}

const forms = [element('#private-form')];
forms[0].value = 'private form value';
const document = {
  hidden: false,
  querySelector: element,
  querySelectorAll(selector) {
    if (selector === 'form') return forms;
    if (selector === 'button' || selector === '.account-home' || selector.includes('input:checked')) return [];
    return [];
  },
  createElement: (tag) => element(`<${tag}>`),
  addEventListener(type, handler) { documentListeners.set(type, handler); },
};
const window = {
  location: {
    origin: 'https://shiftly.test',
    replace(path) { redirects.push(path); },
  },
  addEventListener(type, handler) { windowListeners.set(type, handler); },
  confirm: () => true,
};

async function fetch() {
  fetches += 1;
  if (responseKind === 'unauthenticated') {
    return { ok: true, status: 200, json: async () => ({ authenticated: false }) };
  }
  const status = Number(responseKind);
  return {
    ok: false,
    status,
    json: async () => ({ error: 'Session revoked' }),
  };
}

const context = vm.createContext({
  console, document, window, fetch, Error, JSON, Number, String, Boolean,
  encodeURIComponent, setTimeout, clearTimeout,
});
vm.runInContext(source, context, { filename: 'accounts.js' });

async function settle() {
  for (let index = 0; index < 8; index += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

(async () => {
  await settle();
  await windowListeners.get('focus')();
  await documentListeners.get('visibilitychange')();
  await windowListeners.get('pageshow')();
  await settle();

  const result = {
    redirects,
    fetches,
    invitation: element('#invitation-code').value,
    roster: element('#team-list').textContent + element('#team-list').innerHTML,
    form: forms[0].value,
  };
  process.stdout.write(JSON.stringify(result));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""


@pytest.mark.parametrize("response_kind", ["401", "403", "unauthenticated"])
def test_revoked_session_redirects_once_and_stops_refreshing(response_kind):
    node = os.environ.get("NATIVE_TEST_NODE", "node")
    result = subprocess.run(
        [node, "-e", HARNESS, str(ROOT / "accounts.js"), response_kind],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "redirects": ["/"],
        "fetches": 1,
        "invitation": "",
        "roster": "",
        "form": "",
    }
