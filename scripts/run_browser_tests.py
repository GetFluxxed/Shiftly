#!/usr/bin/env python3
"""Run the browser suite with the pinned Chromium project."""

import subprocess
import sys


def main():
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/browser",
        "--browser",
        "chromium",
        *sys.argv[1:],
    ]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()
