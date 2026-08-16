#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "backend/packages/harness/deerflow/community/douyin_openapi/catalog_snapshot.json"
)
OUTPUT = (
    ROOT
    / "docs/content-intelligence-v6/evidence/douyin-openapi-catalog-2026-08-16.md"
)


def _count_table(title: str, values: Counter[str]) -> list[str]:
    lines = [f"## {title}", "", "| Value | Count |", "| --- | ---: |"]
    lines.extend(f"| {name} | {count} |" for name, count in sorted(values.items()))
    lines.append("")
    return lines


def render(payload: dict) -> str:
    entries = payload["entries"]
    lines = [
        "# Douyin OpenAPI Catalog Evidence",
        "",
        f"- Captured: `{payload['captured_at']}`",
        f"- Official index: {payload['source_url']}",
        f"- Catalog rows: `{payload['source_row_count']}`",
        f"- Source SHA-256: `{payload['source_sha256']}`",
        f"- Entries SHA-256: `{payload['entries_sha256']}`",
        "- Boundary: a catalog row is not a claim that the current app can call it.",
        "",
    ]
    dimensions = (
        ("Official Sections", Counter(entry["section"] for entry in entries)),
        ("Gateway Domains", Counter(entry["domain"] for entry in entries)),
        (
            "Interaction Directions",
            Counter(entry["interaction_direction"] for entry in entries),
        ),
        (
            "Documentation Status",
            Counter(entry["documentation_status"] for entry in entries),
        ),
        ("Review Status", Counter(entry["review_status"] for entry in entries)),
    )
    for title, counts in dimensions:
        lines.extend(_count_table(title, counts))

    lines.extend(
        [
            "## Full Inventory",
            "",
            "| Domain | Capability | Direction | Review | Docs | Method | Scope | Official page |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for entry in entries:
        name = entry["name_zh"].replace("|", "\\|")
        scope = (entry.get("scope") or "-").replace("|", "\\|")
        method = entry.get("http_method") or "-"
        lines.append(
            "| {domain} | {name} | {direction} | {review} | {docs} | "
            "{method} | {scope} | [docs]({url}) |".format(
                domain=entry["domain"],
                name=name,
                direction=entry["interaction_direction"],
                review=entry["review_status"],
                docs=entry["documentation_status"],
                method=method,
                scope=scope,
                url=entry["documentation_url"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rendered = render(payload)
    if args.check:
        return 0 if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == rendered else 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
