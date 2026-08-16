from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, field_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr

_CEDICT_DOWNLOAD_URI = "https://www.mdbg.net/chinese/dictionary?page=cc-cedict"
_CEDICT_LINE = re.compile(r"^(?P<traditional>\S+)\s+(?P<simplified>\S+)\s+\[(?P<pinyin>[^\]]+)]\s+/(?P<definitions>.*)/$")
_MAX_SOURCE_LINE_CHARS = 8_192
_MAX_TERM_CHARS = 64
_MAX_PINYIN_CHARS = 256
_MAX_GLOSS_CHARS = 240
_MAX_GLOSSES_PER_ENTRY = 8
_MAX_INDEX_QUERY_ROWS = 512
_INDEX_SCHEMA_VERSION = 1


class LexicalEvidenceMode(StrEnum):
    EXACT = "exact"
    RELATIONS = "relations"


class LexicalEvidenceSource(ContractModel):
    name: NonEmptyStr
    version: NonEmptyStr
    license: NonEmptyStr
    source_uri: NonEmptyStr
    content_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("content_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("content_sha256 must be lowercase hexadecimal")
        return value


class LexicalIndexReceipt(LexicalEvidenceSource):
    entry_count: int = Field(ge=0)
    skipped_line_count: int = Field(ge=0)


class LexicalEntryEvidence(ContractModel):
    term: NonEmptyStr
    traditional: NonEmptyStr
    pinyin: NonEmptyStr
    glosses: tuple[NonEmptyStr, ...] = ()
    composition_hint: Literal["loanword_or_transliteration"] | None = None


class LexicalRelatedExpression(ContractModel):
    term: NonEmptyStr
    relation: Literal["prefix_extension", "suffix_extension", "infix_extension"]
    glosses: tuple[NonEmptyStr, ...] = ()
    supports_component_glosses: tuple[NonEmptyStr, ...] = ()


class LexicalComponentEvidence(ContractModel):
    term: NonEmptyStr
    positions: tuple[int, ...]
    entries: tuple[LexicalEntryEvidence, ...]
    related_expressions: tuple[LexicalRelatedExpression, ...] = ()


class LexicalEvidence(ContractModel):
    lexical_head: NonEmptyStr
    mode: LexicalEvidenceMode
    source: LexicalEvidenceSource
    whole_word_entries: tuple[LexicalEntryEvidence, ...] = ()
    component_candidates: tuple[LexicalComponentEvidence, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    def to_model_payload(self, *, max_bytes: int = 7_000) -> dict[str, object]:
        if max_bytes < 1_024:
            raise ValueError("lexical evidence model payload budget must be at least 1024 bytes")
        payload = self.model_dump(mode="json", exclude_none=True)
        payload["source"] = {
            "name": self.source.name,
            "version": self.source.version,
            "license": self.source.license,
            "source_uri": self.source.source_uri,
            "content_sha256": self.source.content_sha256,
        }
        _prune_payload_to_budget(payload, max_bytes=max_bytes)
        return payload


class LexicalEvidenceProvider(Protocol):
    async def lookup(
        self,
        lexical_head: str,
        *,
        mode: LexicalEvidenceMode = LexicalEvidenceMode.RELATIONS,
    ) -> LexicalEvidence: ...


class CedictLexicalEvidenceProvider:
    def __init__(
        self,
        index_path: str | Path,
        *,
        max_exact_entries: int = 4,
        max_related_expressions: int = 16,
        max_payload_bytes: int = 7_000,
    ) -> None:
        self._index_path = Path(index_path).expanduser().resolve()
        if not self._index_path.is_file():
            raise ValueError("CC-CEDICT lexical index does not exist")
        if max_exact_entries < 1:
            raise ValueError("max_exact_entries must be positive")
        if max_related_expressions < 0:
            raise ValueError("max_related_expressions cannot be negative")
        if max_payload_bytes < 1_024:
            raise ValueError("max_payload_bytes must be at least 1024")
        self._max_exact_entries = max_exact_entries
        self._max_related_expressions = max_related_expressions
        self._max_payload_bytes = max_payload_bytes
        self._source = self._read_source_receipt()

    @property
    def source(self) -> LexicalEvidenceSource:
        return self._source

    async def lookup(
        self,
        lexical_head: str,
        *,
        mode: LexicalEvidenceMode = LexicalEvidenceMode.RELATIONS,
    ) -> LexicalEvidence:
        normalized = lexical_head.strip()
        if not normalized:
            raise ValueError("lexical_head cannot be empty")
        return await asyncio.to_thread(self._lookup_sync, normalized, LexicalEvidenceMode(mode))

    def render_model_payload(self, evidence: LexicalEvidence) -> str:
        return json.dumps(
            evidence.to_model_payload(max_bytes=self._max_payload_bytes),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _lookup_sync(self, lexical_head: str, mode: LexicalEvidenceMode) -> LexicalEvidence:
        with self._connect() as connection:
            whole_word_entries = self._exact_entries(connection, lexical_head)
            opaque = any(entry.composition_hint == "loanword_or_transliteration" for entry in whole_word_entries)
            component_candidates: tuple[LexicalComponentEvidence, ...]
            if opaque:
                component_candidates = ()
            else:
                component_candidates = tuple(self._component_evidence(connection, lexical_head, term, positions, mode) for term, positions in _strict_substrings(lexical_head) if self._has_exact_entry(connection, term))

        limitations = (
            "词典义项与构词关系只是词义证据，不能单独证明当前语境采用哪个义项。",
            "相同字形不等于意义连续；必须结合整词义项排除借词、音译和机械拆字。",
            "词库缺失只表示未知，不是该词义或关系不存在的证明。",
        )
        return LexicalEvidence(
            lexical_head=lexical_head,
            mode=mode,
            source=self._source,
            whole_word_entries=whole_word_entries,
            component_candidates=component_candidates,
            limitations=limitations,
        )

    def _component_evidence(
        self,
        connection: sqlite3.Connection,
        lexical_head: str,
        term: str,
        positions: tuple[int, ...],
        mode: LexicalEvidenceMode,
    ) -> LexicalComponentEvidence:
        entries = self._exact_entries(connection, term)
        related = ()
        if mode == LexicalEvidenceMode.RELATIONS and self._max_related_expressions:
            related = self._related_expressions(
                connection,
                lexical_head,
                term,
                component_entries=entries,
            )
        return LexicalComponentEvidence(
            term=term,
            positions=positions,
            entries=entries,
            related_expressions=related,
        )

    def _exact_entries(
        self,
        connection: sqlite3.Connection,
        term: str,
    ) -> tuple[LexicalEntryEvidence, ...]:
        rows = connection.execute(
            "SELECT traditional, simplified, pinyin, glosses_json FROM entries WHERE simplified = ? ORDER BY id LIMIT ?",
            (term, self._max_exact_entries),
        ).fetchall()
        return tuple(_entry_from_row(row) for row in rows)

    @staticmethod
    def _has_exact_entry(connection: sqlite3.Connection, term: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM entries WHERE simplified = ? LIMIT 1",
                (term,),
            ).fetchone()
            is not None
        )

    def _related_expressions(
        self,
        connection: sqlite3.Connection,
        lexical_head: str,
        component: str,
        *,
        component_entries: tuple[LexicalEntryEvidence, ...],
    ) -> tuple[LexicalRelatedExpression, ...]:
        rows = connection.execute(
            """
            SELECT traditional, simplified, pinyin, glosses_json
            FROM entries
            WHERE simplified != ?
              AND simplified != ?
              AND instr(simplified, ?) > 0
              AND length(simplified) <= 12
            ORDER BY length(simplified), simplified, id
            LIMIT ?
            """,
            (component, lexical_head, component, _MAX_INDEX_QUERY_ROWS),
        ).fetchall()
        relation_seed_entries = tuple(entry for entry in component_entries if not _is_proper_name_entry(entry)) or component_entries
        component_glosses = tuple(dict.fromkeys(gloss for entry in relation_seed_entries for gloss in entry.glosses if _meaning_tokens(gloss)))
        candidates: list[LexicalRelatedExpression] = []
        seen_terms: set[str] = set()
        for row in rows:
            entry = _entry_from_row(row)
            if _is_proper_name_entry(entry):
                continue
            if entry.term in seen_terms:
                continue
            seen_terms.add(entry.term)
            if entry.term.startswith(component):
                relation = "prefix_extension"
            elif entry.term.endswith(component):
                relation = "suffix_extension"
            else:
                relation = "infix_extension"
            related_tokens = set().union(*(_meaning_tokens(gloss) for gloss in entry.glosses))
            supported_glosses = tuple(gloss for gloss in component_glosses if related_tokens.intersection(_meaning_tokens(gloss)))
            candidates.append(
                LexicalRelatedExpression(
                    term=entry.term,
                    relation=relation,
                    glosses=entry.glosses[:3],
                    supports_component_glosses=supported_glosses[:3],
                )
            )
        candidates.sort(
            key=lambda item: (
                {"prefix_extension": 0, "suffix_extension": 1, "infix_extension": 2}[item.relation],
                len(item.term),
                item.term,
            )
        )
        return _select_sense_balanced_relations(
            candidates,
            component_glosses=component_glosses,
            limit=self._max_related_expressions,
        )

    def _read_source_receipt(self) -> LexicalEvidenceSource:
        with self._connect() as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
        if metadata.get("schema_version") != str(_INDEX_SCHEMA_VERSION):
            raise ValueError("unsupported CC-CEDICT lexical index schema")
        return LexicalEvidenceSource(
            name=metadata["source_name"],
            version=metadata["source_version"],
            license=metadata["license"],
            source_uri=metadata["source_uri"],
            content_sha256=metadata["content_sha256"],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._index_path)
        connection.execute("PRAGMA query_only = ON")
        return connection


def build_cc_cedict_index(
    source_path: str | Path,
    index_path: str | Path,
) -> LexicalIndexReceipt:
    source = Path(source_path).expanduser().resolve()
    target = Path(index_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError("CC-CEDICT source file does not exist")
    target.parent.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, str] = {}
    digest = hashlib.sha256()
    skipped_line_count = 0
    entry_count = 0
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        with sqlite3.connect(temporary_path) as connection:
            _initialize_index(connection)
            pending_rows: list[tuple[str, str, str, str]] = []
            for line, oversized in _iter_source_lines(source):
                digest.update(line.encode("utf-8"))
                digest.update(b"\n")
                if oversized:
                    skipped_line_count += 1
                    continue
                if line.startswith("#! "):
                    key, separator, value = line[3:].partition("=")
                    if separator:
                        metadata[key.strip()] = value.strip()
                    continue
                if not line or line.startswith("#"):
                    continue
                parsed = _parse_cedict_line(line)
                if parsed is None:
                    skipped_line_count += 1
                    continue
                pending_rows.append(parsed)
                if len(pending_rows) >= 1_000:
                    connection.executemany(
                        "INSERT INTO entries (traditional, simplified, pinyin, glosses_json) VALUES (?, ?, ?, ?)",
                        pending_rows,
                    )
                    entry_count += len(pending_rows)
                    pending_rows.clear()
            if pending_rows:
                connection.executemany(
                    "INSERT INTO entries (traditional, simplified, pinyin, glosses_json) VALUES (?, ?, ?, ?)",
                    pending_rows,
                )
                entry_count += len(pending_rows)

            receipt = _index_receipt(
                metadata,
                content_sha256=digest.hexdigest(),
                entry_count=entry_count,
                skipped_line_count=skipped_line_count,
            )
            index_metadata = {
                "schema_version": str(_INDEX_SCHEMA_VERSION),
                "source_name": receipt.name,
                "source_version": receipt.version,
                "license": receipt.license,
                "source_uri": receipt.source_uri,
                "content_sha256": receipt.content_sha256,
                "entry_count": str(receipt.entry_count),
                "skipped_line_count": str(receipt.skipped_line_count),
            }
            connection.executemany(
                "INSERT INTO metadata (key, value) VALUES (?, ?)",
                tuple(index_metadata.items()),
            )
            connection.commit()
        os.replace(temporary_path, target)
        return receipt
    finally:
        temporary_path.unlink(missing_ok=True)


def _initialize_index(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY,
            traditional TEXT NOT NULL,
            simplified TEXT NOT NULL,
            pinyin TEXT NOT NULL,
            glosses_json TEXT NOT NULL
        );
        CREATE INDEX idx_entries_simplified ON entries (simplified);
        """
    )


def _iter_source_lines(path: Path) -> Iterator[tuple[str, bool]]:
    opener = gzip.open if path.suffix.casefold() == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="strict", newline=None) as stream:
        for raw_line in stream:
            line = raw_line.rstrip("\r\n")
            yield line, len(line) > _MAX_SOURCE_LINE_CHARS


def _parse_cedict_line(line: str) -> tuple[str, str, str, str] | None:
    match = _CEDICT_LINE.fullmatch(line)
    if match is None:
        return None
    traditional = match.group("traditional")
    simplified = match.group("simplified")
    pinyin = match.group("pinyin")
    if not traditional or not simplified or len(traditional) > _MAX_TERM_CHARS or len(simplified) > _MAX_TERM_CHARS or len(pinyin) > _MAX_PINYIN_CHARS:
        return None
    glosses = tuple(definition.strip()[:_MAX_GLOSS_CHARS] for definition in match.group("definitions").split("/") if definition.strip())
    if not glosses or any(len(definition) > _MAX_GLOSS_CHARS for definition in match.group("definitions").split("/") if definition.strip()):
        return None
    return traditional, simplified, pinyin, json.dumps(glosses[:_MAX_GLOSSES_PER_ENTRY], ensure_ascii=False, separators=(",", ":"))


def _index_receipt(
    metadata: dict[str, str],
    *,
    content_sha256: str,
    entry_count: int,
    skipped_line_count: int,
) -> LexicalIndexReceipt:
    version = metadata.get("version", "unknown")
    subversion = metadata.get("subversion")
    if subversion:
        version = f"{version}.{subversion}"
    if date := metadata.get("date"):
        version = f"{version}+{date}"
    license_uri = metadata.get("license", "")
    license_name = "CC BY-SA 4.0" if "creativecommons.org/licenses/by-sa/4.0" in license_uri else license_uri or "unknown"
    return LexicalIndexReceipt(
        name="CC-CEDICT",
        version=version,
        license=license_name,
        source_uri=_CEDICT_DOWNLOAD_URI,
        content_sha256=content_sha256,
        entry_count=entry_count,
        skipped_line_count=skipped_line_count,
    )


def _entry_from_row(row: tuple[str, str, str, str]) -> LexicalEntryEvidence:
    traditional, simplified, pinyin, glosses_json = row
    glosses = tuple(json.loads(glosses_json))
    normalized_glosses = " ".join(glosses).casefold()
    composition_hint = None
    if "loanword" in normalized_glosses or "transliteration" in normalized_glosses:
        composition_hint = "loanword_or_transliteration"
    return LexicalEntryEvidence(
        term=simplified,
        traditional=traditional,
        pinyin=pinyin,
        glosses=glosses,
        composition_hint=composition_hint,
    )


def _strict_substrings(term: str) -> tuple[tuple[str, tuple[int, ...]], ...]:
    positions_by_term: dict[str, list[int]] = {}
    for length in range(len(term) - 1, 0, -1):
        for start in range(0, len(term) - length + 1):
            candidate = term[start : start + length]
            positions_by_term.setdefault(candidate, []).append(start)
    return tuple((candidate, tuple(positions)) for candidate, positions in positions_by_term.items())


def _meaning_tokens(text: str) -> frozenset[str]:
    stopwords = {
        "a",
        "abbr",
        "an",
        "and",
        "cl",
        "for",
        "in",
        "of",
        "one",
        "or",
        "sb",
        "see",
        "sth",
        "the",
        "to",
        "variant",
    }
    normalized: set[str] = set()
    for token in re.findall(r"[a-z]+", text.casefold()):
        if token in stopwords or len(token) < 3:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        normalized.add(token)
    return frozenset(normalized)


def _is_proper_name_entry(entry: LexicalEntryEvidence) -> bool:
    first_letter = re.search(r"[A-Za-z]", entry.pinyin)
    return first_letter is not None and first_letter.group(0).isupper()


def _select_sense_balanced_relations(
    candidates: list[LexicalRelatedExpression],
    *,
    component_glosses: tuple[str, ...],
    limit: int,
) -> tuple[LexicalRelatedExpression, ...]:
    if limit <= 0:
        return ()
    selected: list[LexicalRelatedExpression] = []
    selected_terms: set[str] = set()

    made_progress = True
    while len(selected) < limit and made_progress:
        made_progress = False
        for gloss in component_glosses:
            candidate = next(
                (item for item in candidates if item.term not in selected_terms and gloss in item.supports_component_glosses),
                None,
            )
            if candidate is None:
                continue
            selected.append(candidate)
            selected_terms.add(candidate.term)
            made_progress = True
            if len(selected) >= limit:
                break

    for candidate in candidates:
        if len(selected) >= limit:
            break
        if candidate.term in selected_terms:
            continue
        selected.append(candidate)
        selected_terms.add(candidate.term)
    return tuple(selected)


def _prune_payload_to_budget(payload: dict[str, object], *, max_bytes: int) -> None:
    def size() -> int:
        return _payload_size(payload)

    components = payload.get("component_candidates")
    if not isinstance(components, list):
        components = []
    while size() > max_bytes:
        related_lists = [component.get("related_expressions") for component in components if isinstance(component, dict)]
        populated = [items for items in related_lists if isinstance(items, list) and items]
        if populated:
            max(populated, key=len).pop()
            continue
        gloss_lists: list[list[object]] = []
        for entry in payload.get("whole_word_entries", []):
            if isinstance(entry, dict) and isinstance(entry.get("glosses"), list) and len(entry["glosses"]) > 1:
                gloss_lists.append(entry["glosses"])
        for component in components:
            if not isinstance(component, dict):
                continue
            for entry in component.get("entries", []):
                if isinstance(entry, dict) and isinstance(entry.get("glosses"), list) and len(entry["glosses"]) > 1:
                    gloss_lists.append(entry["glosses"])
        if gloss_lists:
            max(gloss_lists, key=len).pop()
            continue
        if len(components) > 1:
            components.pop()
            continue
        limitations = payload.get("limitations")
        if isinstance(limitations, list) and len(limitations) > 1:
            limitations.pop()
            continue
        break

    if size() > max_bytes:
        raise ValueError("lexical evidence minimum payload exceeds configured budget")


def _payload_size(payload: dict[str, object]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
