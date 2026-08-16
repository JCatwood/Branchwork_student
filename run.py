#!/usr/bin/env python3
"""Start the local homework application."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "src" / "app"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    loopback_hosts = {"127.0.0.1", "localhost", "::1", "[::1]"}
    if args.host not in loopback_hosts:
        parser.error(
            "Branchwork Git controls may only be served on the local computer"
        )

    subprocess.run(
        [
            sys.executable,
            str(APP_DIR / "manage.py"),
            "runserver",
            f"{args.host}:{args.port}",
            "--noreload",
        ],
        cwd=APP_DIR,
        check=True,
    )


if __name__ == "__main__":
    main()
