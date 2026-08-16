#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend/packages/harness"
sys.path.insert(0, str(HARNESS))

from deerflow.content_intelligence.lexical_evidence import build_cc_cedict_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the local read-only CC-CEDICT index used by content intelligence.",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Official CC-CEDICT .txt or .txt.gz release downloaded from MDBG.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "backend/.deer-flow/lexicons/cc-cedict.sqlite3",
        help="Gitignored SQLite output path.",
    )
    args = parser.parse_args()
    receipt = build_cc_cedict_index(args.source, args.output)
    print(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
