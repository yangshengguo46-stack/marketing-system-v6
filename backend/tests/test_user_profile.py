from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.agents.user_profile import (
    MAX_USER_PROFILE_ITEMS,
    FileUserProfileStore,
    UserProfileConflict,
    UserProfileMutationSource,
)
from deerflow.config.paths import Paths


def _source(*, suffix: str = "1") -> UserProfileMutationSource:
    return UserProfileMutationSource(
        thread_id=f"thread-{suffix}",
        run_id=f"run-{suffix}",
        message_id=f"message-{suffix}",
        message_sha256="a" * 64,
        excerpt_sha256="b" * 64,
        recorded_at=datetime(2026, 8, 23, 8, int(suffix) if suffix.isdigit() else 0, tzinfo=UTC),
    )


def test_profile_revisions_are_owner_scoped_content_addressed_and_correctable(tmp_path) -> None:
    paths = Paths(tmp_path)
    store = FileUserProfileStore(paths)

    assert store.load("user-a") is None

    remembered = store.remember(
        "user-a",
        kind="background",
        statement="我不懂代码",
        source=_source(),
    )
    first = remembered.revision
    assert remembered.changed is True
    assert first.version == 1
    assert first.previous_content_sha256 is None
    assert first.items[0].statement == "我不懂代码"
    assert first.content_sha256 == first.calculate_content_sha256()
    assert store.load("user-b") is None

    replaced = store.replace(
        "user-a",
        item_id=remembered.item_id,
        kind="background",
        statement="我现在能看懂一点代码",
        source=_source(suffix="2"),
        expected_version=1,
    )
    second = replaced.revision
    assert second.version == 2
    assert second.previous_content_sha256 == first.content_sha256
    assert second.items[0].item_id == remembered.item_id
    assert second.items[0].statement == "我现在能看懂一点代码"

    forgotten = store.forget(
        "user-a",
        item_id=remembered.item_id,
        source=_source(suffix="3"),
        expected_version=2,
    )
    assert forgotten.revision.version == 3
    assert forgotten.revision.items == ()
    assert store.load("user-a") == forgotten.revision


def test_duplicate_remember_is_idempotent_and_stale_expected_version_conflicts(tmp_path) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    first = store.remember(
        "user-a",
        kind="communication_preference",
        statement="请用中文跟我说",
        source=_source(),
        expected_version=0,
    )
    duplicate = store.remember(
        "user-a",
        kind="communication_preference",
        statement="请用中文跟我说",
        source=_source(suffix="2"),
        expected_version=1,
    )

    assert duplicate.changed is False
    assert duplicate.item_id == first.item_id
    assert duplicate.revision.version == 1

    with pytest.raises(UserProfileConflict, match="expected profile version 0"):
        store.remember(
            "user-a",
            kind="background",
            statement="我不懂代码",
            source=_source(suffix="3"),
            expected_version=0,
        )


def test_profile_has_a_small_hard_item_limit(tmp_path) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    for index in range(MAX_USER_PROFILE_ITEMS):
        store.remember(
            "user-a",
            kind="collaboration_preference",
            statement=f"稳定偏好 {index}",
            source=_source(suffix=str((index % 9) + 1)),
        )

    with pytest.raises(ValueError, match="at most"):
        store.remember(
            "user-a",
            kind="background",
            statement="超出上限",
            source=_source(),
        )


def test_tampered_revision_fails_closed_instead_of_becoming_prompt_context(tmp_path) -> None:
    paths = Paths(tmp_path)
    store = FileUserProfileStore(paths)
    store.remember(
        "user-a",
        kind="background",
        statement="我不懂代码",
        source=_source(),
    )
    revision_path = paths.user_profile_revisions_dir("user-a") / "00000001.json"
    raw = revision_path.read_text(encoding="utf-8").replace("我不懂代码", "被篡改的内容")
    revision_path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="content_sha256"):
        store.load("user-a")
