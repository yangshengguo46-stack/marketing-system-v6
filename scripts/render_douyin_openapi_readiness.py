#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend/packages/harness"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from deerflow.community.douyin_openapi.catalog import load_official_catalog  # noqa: E402
from deerflow.community.douyin_openapi.readiness import (  # noqa: E402
    build_capability_readiness,
    render_capability_readiness_markdown,
)

OBSERVATION = (
    ROOT
    / "docs/content-intelligence-v6/evidence/douyin-openapi-live-observation-2026-08-19.json"
)
OUTPUT = (
    ROOT
    / "docs/content-intelligence-v6/evidence/douyin-openapi-readiness-2026-08-19.md"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    observation = json.loads(OBSERVATION.read_text(encoding="utf-8"))
    report = build_capability_readiness(load_official_catalog(), observation)
    rendered = render_capability_readiness_markdown(report)
    if args.check:
        return 0 if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == rendered else 1
    OUTPUT.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
