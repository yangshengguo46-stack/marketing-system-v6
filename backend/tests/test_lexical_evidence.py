from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from deerflow.content_intelligence.lexical_evidence import (
    CedictLexicalEvidenceProvider,
    LexicalEvidenceMode,
    build_cc_cedict_index,
)

CEDICT_SAMPLE = """# CC-CEDICT
#! version=1
#! subversion=0
#! entries=19
#! publisher=MDBG
#! license=https://creativecommons.org/licenses/by-sa/4.0/
#! date=2026-08-15T06:33:03Z
禮 礼 [li3] /gift/rite/ceremony/CL:份[fen4]/propriety/etiquette/courtesy/
禮 礼 [Li3] /surname Li/abbr. for 禮記|礼记[Li3 ji4], Classic of Rites/
禮品 礼品 [li3 pin3] /gift/present/
禮樂 礼乐 [li3 yue4] /(Confucianism) rites and music (the means of regulating society)/
禮儀 礼仪 [li3 yi2] /etiquette/ceremony/
禮制 礼制 [li3 zhi4] /etiquette/system of rites/
禮尚往來 礼尚往来 [li3 shang4 wang3 lai2] /proper behavior is based on reciprocity/
禮崩樂壞 礼崩乐坏 [li3 beng1 yue4 huai4] /rites and music are in ruins/society in total disarray/
禮貌 礼貌 [li3 mao4] /courtesy/politeness/manners/
禮縣 礼县 [Li3 xian4] /Li County in Gansu/
品 品 [pin3] /article/product/commodity/goods/
海鮮 海鲜 [hai3 xian1] /seafood/
海 海 [hai3] /ocean/sea/
鮮 鲜 [xian1] /fresh/bright/delicious/
火鍋 火锅 [huo3 guo1] /hotpot/
火 火 [huo3] /fire/
鍋 锅 [guo1] /pot/pan/
雪茄 雪茄 [xue3 jia1] /(loanword) cigar/
咖啡 咖啡 [ka1 fei1] /(loanword) coffee/
"""


@pytest.fixture()
def cedict_index(tmp_path: Path) -> Path:
    source_path = tmp_path / "cedict.txt.gz"
    with gzip.open(source_path, "wt", encoding="utf-8", newline="\n") as stream:
        stream.write(CEDICT_SAMPLE)
    index_path = tmp_path / "cedict.sqlite3"
    receipt = build_cc_cedict_index(source_path, index_path)
    assert receipt.entry_count == 19
    return index_path


@pytest.mark.asyncio
async def test_exact_evidence_keeps_whole_word_and_strict_subcomponent_senses(cedict_index: Path) -> None:
    provider = CedictLexicalEvidenceProvider(cedict_index)

    evidence = await provider.lookup("礼品", mode=LexicalEvidenceMode.EXACT)

    assert provider.source.content_sha256 == evidence.source.content_sha256
    assert evidence.lexical_head == "礼品"
    assert evidence.source.name == "CC-CEDICT"
    assert evidence.source.version == "1.0+2026-08-15T06:33:03Z"
    assert evidence.source.license == "CC BY-SA 4.0"
    assert [entry.term for entry in evidence.whole_word_entries] == ["礼品"]
    assert [component.term for component in evidence.component_candidates] == ["礼", "品"]
    assert "propriety" in evidence.component_candidates[0].entries[0].glosses
    assert all(not component.related_expressions for component in evidence.component_candidates)


@pytest.mark.asyncio
async def test_relation_evidence_returns_bounded_typed_lexical_family(cedict_index: Path) -> None:
    provider = CedictLexicalEvidenceProvider(cedict_index, max_related_expressions=4)

    evidence = await provider.lookup("礼品", mode=LexicalEvidenceMode.RELATIONS)

    gift_rite = next(component for component in evidence.component_candidates if component.term == "礼")
    related = {item.term: item.relation for item in gift_rite.related_expressions}
    support = {item.term: item.supports_component_glosses for item in gift_rite.related_expressions}
    assert related["礼仪"] == "prefix_extension"
    assert related["礼制"] == "prefix_extension"
    assert set(related) == {"礼乐", "礼仪", "礼制", "礼貌"}
    assert "etiquette" in support["礼仪"]
    assert "courtesy" in support["礼貌"]
    assert len(gift_rite.related_expressions) == 4
    assert "礼品" not in related


@pytest.mark.asyncio
async def test_proper_name_senses_are_visible_but_do_not_seed_component_relations(
    cedict_index: Path,
) -> None:
    provider = CedictLexicalEvidenceProvider(cedict_index, max_related_expressions=20)

    evidence = await provider.lookup("礼品", mode=LexicalEvidenceMode.RELATIONS)

    gift_rite = next(component for component in evidence.component_candidates if component.term == "礼")
    assert any(entry.pinyin == "Li3" for entry in gift_rite.entries)
    assert "礼县" not in {item.term for item in gift_rite.related_expressions}


@pytest.mark.asyncio
async def test_opaque_loanword_signal_is_preserved_without_inventing_a_component_relation(
    cedict_index: Path,
) -> None:
    provider = CedictLexicalEvidenceProvider(cedict_index)

    evidence = await provider.lookup("雪茄", mode=LexicalEvidenceMode.RELATIONS)

    assert evidence.whole_word_entries[0].glosses == ("(loanword) cigar",)
    assert evidence.whole_word_entries[0].composition_hint == "loanword_or_transliteration"
    assert evidence.component_candidates == ()


@pytest.mark.asyncio
async def test_evidence_payload_is_bounded_and_never_exposes_the_local_index_path(
    cedict_index: Path,
) -> None:
    provider = CedictLexicalEvidenceProvider(
        cedict_index,
        max_related_expressions=100,
        max_payload_bytes=1_600,
    )

    evidence = await provider.lookup("礼品", mode=LexicalEvidenceMode.RELATIONS)
    payload = evidence.to_model_payload(max_bytes=1_600)
    rendered = provider.render_model_payload(evidence)

    assert len(rendered.encode("utf-8")) <= 1_600
    assert str(cedict_index) not in rendered
    assert payload["source"]["content_sha256"]
    assert payload["limitations"]


def test_index_builder_skips_malformed_or_oversized_untrusted_lines(tmp_path: Path) -> None:
    source_path = tmp_path / "cedict.txt"
    source_path.write_text(
        CEDICT_SAMPLE + "bad line pretending to be data\n" + f"惡 恶 [e4] /{'x' * 20_000}/\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "cedict.sqlite3"

    receipt = build_cc_cedict_index(source_path, index_path)

    assert receipt.entry_count == 19
    assert receipt.skipped_line_count == 2
