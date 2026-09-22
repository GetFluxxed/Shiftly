"""A failed backup or restore must never produce a successful rehearsal."""

import subprocess

import pytest

from scripts import rehearse_release as rehearsal


SOURCE = "postgresql://test:source-secret@127.0.0.1:5432/source"
TARGET = "postgresql://test:target-secret@127.0.0.1:5432/restore"


def test_missing_clients_fail_before_touching_a_database(monkeypatch):
    monkeypatch.setattr(rehearsal.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        rehearsal.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("No database command should run."),
    )
    with pytest.raises(RuntimeError, match="pg_dump is required"):
        rehearsal.backup_restore(SOURCE, TARGET)


def test_restore_into_source_is_rejected_even_with_different_credentials(monkeypatch):
    monkeypatch.setattr(
        rehearsal.subprocess, "run",
        lambda *args, **kwargs: pytest.fail("Source must not be overwritten."),
    )
    with pytest.raises(RuntimeError, match="separate disposable databases"):
        rehearsal.backup_restore(SOURCE, SOURCE.replace("source-secret", "other-secret"))


@pytest.mark.parametrize("failed_stage", ["backup", "restore"])
@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_command_failure_is_fatal_and_redacted(monkeypatch, failed_stage, failure):
    monkeypatch.setattr(rehearsal.shutil, "which", lambda tool: tool)
    calls = []

    def run(command, **kwargs):
        calls.append(command[0])
        stage = "backup" if command[0] == "pg_dump" else "restore"
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 60
        if stage == failed_stage:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(command, 60, stderr=b"source-secret")
            raise subprocess.CalledProcessError(1, command, stderr=b"target-secret")
        kwargs["stdout"].write(b"archive")

    monkeypatch.setattr(rehearsal.subprocess, "run", run)
    with pytest.raises(RuntimeError, match=f"PostgreSQL {failed_stage} failed") as error:
        rehearsal.backup_restore(SOURCE, TARGET)
    assert "secret" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert calls == (["pg_dump"] if failed_stage == "backup" else ["pg_dump", "pg_restore"])


def test_container_clients_preserve_archive_and_require_atomic_restore(monkeypatch):
    monkeypatch.setattr(rehearsal.shutil, "which", lambda tool: tool)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[:3] == ["docker", "exec", "-i"]
        if command[4] == "pg_dump":
            assert command[3] == "source-db"
            assert "--format=custom" in command
            kwargs["stdout"].write(b"actual archive bytes")
        else:
            assert command[3:5] == ["restore-db", "pg_restore"]
            assert "--exit-on-error" in command
            assert "--single-transaction" in command
            assert kwargs["stdin"].read() == b"actual archive bytes"

    monkeypatch.setattr(rehearsal.subprocess, "run", run)
    assert rehearsal.backup_restore(
        SOURCE, TARGET, source_container="source-db", restore_container="restore-db"
    ) == len(b"actual archive bytes")
    assert len(calls) == 2
