from pathlib import Path

import pytest

from scripts.verify_dependency_locks import LockError, read_lock


def write_lock(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "requirements.lock"
    path.write_text(content, encoding="utf-8")
    return path


def test_lock_rejects_missing_transitive_pin(tmp_path, monkeypatch):
    from scripts import verify_dependency_locks

    class Distribution:
        version = "1.0"
        requires = ["child>=2"]

    monkeypatch.setattr(verify_dependency_locks.metadata, "distribution", lambda name: Distribution())
    locked = read_lock(write_lock(tmp_path, "parent==1.0\n"))

    with pytest.raises(LockError, match="unlocked runtime dependency child"):
        verify_dependency_locks.verify_runtime_closure(locked, [verify_dependency_locks.Requirement("parent")])


def test_lock_rejects_duplicate_pin_even_when_versions_match(tmp_path):
    path = write_lock(tmp_path, "child==2.0\nchild==2.0\n")

    with pytest.raises(LockError, match="duplicate lock entry for child"):
        read_lock(path)


def test_runtime_closure_rejects_unrelated_active_pin(tmp_path, monkeypatch):
    from scripts import verify_dependency_locks

    class Distribution:
        version = "1.0"
        requires = []

    monkeypatch.setattr(verify_dependency_locks.metadata, "distribution", lambda name: Distribution())
    locked = read_lock(write_lock(tmp_path, "parent==1.0\nunrelated==1.0\n"))

    with pytest.raises(LockError, match="non-runtime pins: unrelated"):
        verify_dependency_locks.verify_runtime_closure(locked, [verify_dependency_locks.Requirement("parent")])
