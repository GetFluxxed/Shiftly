"""Verify that Shiftly's Python locks are exact, aligned, and dependency-complete."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]


class LockError(ValueError):
    """Raised when a dependency input or lock is inconsistent."""


def _content_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def read_requirements(path: Path, *, allow_include: bool = False) -> list[Requirement]:
    requirements: list[Requirement] = []
    for line in _content_lines(path):
        if line.startswith("-r "):
            if not allow_include:
                raise LockError(f"{path}: includes are not allowed here: {line}")
            continue
        try:
            requirements.append(Requirement(line))
        except ValueError as error:
            raise LockError(f"{path}: invalid requirement {line!r}: {error}") from error
    return requirements


def read_lock(path: Path, *, expected_include: str | None = None) -> dict[str, Requirement]:
    locked: dict[str, Requirement] = {}
    includes: list[str] = []
    for line in _content_lines(path):
        if line.startswith("-r "):
            includes.append(line[3:].strip())
            continue
        requirement = Requirement(line)
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==" or pins[0].version.endswith(".*"):
            raise LockError(f"{path}: lock entry is not an exact pin: {line}")
        name = canonicalize_name(requirement.name)
        if name in locked:
            raise LockError(f"{path}: duplicate lock entry for {name}")
        locked[name] = requirement
    wanted = [expected_include] if expected_include else []
    if includes != wanted:
        raise LockError(f"{path}: expected includes {wanted}, found {includes}")
    return locked


def verify_inputs(inputs: list[Requirement], locked: dict[str, Requirement], source: Path) -> None:
    for requested in inputs:
        name = canonicalize_name(requested.name)
        pin = locked.get(name)
        if pin is None:
            raise LockError(f"{source}: {requested.name} is missing from the matching lock")
        version = Version(next(iter(pin.specifier)).version)
        if version not in requested.specifier:
            raise LockError(f"{source}: locked {requested.name} {version} violates {requested.specifier}")
        if requested.extras - pin.extras:
            missing = ", ".join(sorted(requested.extras - pin.extras))
            raise LockError(f"{source}: lock drops extras for {requested.name}: {missing}")


def _marker_applies(requirement: Requirement, extras: set[str]) -> bool:
    if requirement.marker is None:
        return True
    environments = []
    for extra in extras or {""}:
        environment = default_environment()
        environment["extra"] = extra
        environments.append(environment)
    return any(requirement.marker.evaluate(environment) for environment in environments)


def verify_runtime_closure(locked: dict[str, Requirement], roots: list[Requirement]) -> None:
    extras_by_name: dict[str, set[str]] = defaultdict(set)
    pending: deque[str] = deque()
    for root in roots:
        name = canonicalize_name(root.name)
        extras_by_name[name].update(root.extras)
        pending.append(name)

    visited: set[tuple[str, frozenset[str]]] = set()
    while pending:
        name = pending.popleft()
        extras = extras_by_name[name]
        state = (name, frozenset(extras))
        if state in visited:
            continue
        visited.add(state)
        pin = locked.get(name)
        if pin is None or not _marker_applies(pin, set()):
            raise LockError(f"runtime dependency {name} is not active in requirements.lock")
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError as error:
            raise LockError(f"runtime dependency {name} is not installed") from error
        expected = next(iter(pin.specifier)).version
        if distribution.version != expected:
            raise LockError(f"installed {name}=={distribution.version}; lock requires {expected}")
        for raw_dependency in distribution.requires or []:
            dependency = Requirement(raw_dependency)
            if not _marker_applies(dependency, extras):
                continue
            dependency_name = canonicalize_name(dependency.name)
            dependency_pin = locked.get(dependency_name)
            if dependency_pin is None or not _marker_applies(dependency_pin, set()):
                raise LockError(f"{name} requires unlocked runtime dependency {dependency}")
            dependency_version = Version(next(iter(dependency_pin.specifier)).version)
            if dependency_version not in dependency.specifier:
                raise LockError(
                    f"{name} requires {dependency}; lock pins incompatible {dependency_version}"
                )
            previous_extras = len(extras_by_name[dependency_name])
            extras_by_name[dependency_name].update(dependency.extras)
            if dependency_name not in {item[0] for item in visited} or len(extras_by_name[dependency_name]) != previous_extras:
                pending.append(dependency_name)

    reached = {name for name, _extras in visited}
    active_pins = {name for name, pin in locked.items() if _marker_applies(pin, set())}
    if unused := sorted(active_pins - reached):
        raise LockError(f"requirements.lock contains non-runtime pins: {', '.join(unused)}")


def verify(root: Path = ROOT) -> None:
    runtime_inputs_path = root / "requirements.txt"
    dev_inputs_path = root / "requirements-dev.txt"
    runtime_lock_path = root / "requirements.lock"
    dev_lock_path = root / "requirements-dev.lock"

    runtime_inputs = read_requirements(runtime_inputs_path)
    dev_inputs = read_requirements(dev_inputs_path, allow_include=True)
    runtime_lock = read_lock(runtime_lock_path)
    dev_lock = read_lock(dev_lock_path, expected_include="requirements.lock")

    if overlap := sorted(runtime_lock.keys() & dev_lock.keys()):
        raise LockError(f"requirements-dev.lock duplicates runtime pins: {', '.join(overlap)}")

    if "pytest" in {canonicalize_name(item.name) for item in runtime_inputs}:
        raise LockError("pytest must remain a development-only dependency")
    verify_inputs(runtime_inputs, runtime_lock, runtime_inputs_path)
    verify_inputs(dev_inputs, runtime_lock | dev_lock, dev_inputs_path)
    verify_runtime_closure(runtime_lock, runtime_inputs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to verify")
    args = parser.parse_args()
    try:
        verify(args.root.resolve())
    except LockError as error:
        parser.error(str(error))
    print("Dependency locks are exact, aligned, and complete for this platform.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
