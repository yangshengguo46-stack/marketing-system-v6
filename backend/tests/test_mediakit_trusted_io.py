from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from deerflow.community.mediakit import (
    CommandResult,
    MediaKitCapabilityRouter,
    MediaKitCloudMaterializationContext,
    MediaKitCloudOutputPolicy,
    MediaKitCloudResultMaterializer,
    MediaKitCloudSourceContext,
    MediaKitCommandError,
    MediaKitSafeHttpDownloader,
    MediaKitTrustedSourceStore,
    MediaKitVideoArtifactQualityChecker,
)


def _public_resolver(_hostname: str) -> list[ipaddress._BaseAddress]:
    return [ipaddress.ip_address("93.184.216.34")]


def _source_context(*, source_ref: str, content_sha256: str, rights_ref: str = "rights-1") -> MediaKitCloudSourceContext:
    return MediaKitCloudSourceContext(
        user_id="user-1",
        project_id="project-1",
        local_task_id="task-1",
        source_ref=source_ref,
        rights_ref=rights_ref,
        source_content_sha256=content_sha256,
    )


def _materialization_context(
    *,
    provider_output: dict[str, object],
    provider_output_sha256: str = "e" * 64,
    operation_sha256: str = "d" * 64,
    fee_quote_sha256: str = "8" * 64,
) -> MediaKitCloudMaterializationContext:
    return MediaKitCloudMaterializationContext(
        local_task_id="task-1",
        user_id="user-1",
        project_id="project-1",
        thread_id="thread-1",
        remote_task_id="remote-secret-task",
        source_ref="media-source:source-1",
        rights_ref="rights-1",
        source_content_sha256="a" * 64,
        capability_domain="video",
        capability_tool="enhance-video",
        cli_version="0.2.0",
        capability_schema_sha256="b" * 64,
        request_sha256="c" * 64,
        operation_sha256=operation_sha256,
        client_token_sha256="f" * 64,
        cloud_processing_approval_ref="approval-cloud-1",
        fee_authorization_ref="approval-fee-1",
        currency="CNY",
        maximum_amount_micros=1_000_000,
        pricing_evidence_sha256="9" * 64,
        fee_quote_sha256=fee_quote_sha256,
        estimated_amount_micros=12_500,
        fee_quote_valid_until=datetime(2099, 1, 1, tzinfo=UTC),
        provider_output=provider_output,
        provider_output_sha256=provider_output_sha256,
    )


@pytest.mark.asyncio
async def test_trusted_source_store_stages_content_addressed_video_and_resolves_exact_binding(tmp_path: Path) -> None:
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"stable-video-bytes")
    store = MediaKitTrustedSourceStore(tmp_path / "private-media")

    staged = await store.stage_local_video(
        user_id="user-1",
        project_id="project-1",
        source_path=source_path,
        rights_ref="rights-1",
    )
    repeated = await store.stage_local_video(
        user_id="user-1",
        project_id="project-1",
        source_path=source_path,
        rights_ref="rights-1",
    )

    assert staged == repeated
    assert staged.content_sha256 == hashlib.sha256(b"stable-video-bytes").hexdigest()
    assert staged.source_ref.startswith("media-source:")
    assert str(source_path) not in repr(staged)
    resolved = await store.resolve(
        _source_context(
            source_ref=staged.source_ref,
            content_sha256=staged.content_sha256,
        )
    )
    assert resolved.transport == "local_file"
    assert resolved.source_ref == staged.source_ref
    assert str(tmp_path) not in repr(resolved)
    await store.verify(
        _source_context(
            source_ref=staged.source_ref,
            content_sha256=staged.content_sha256,
        ),
        resolved,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["owner", "project", "rights", "hash", "source_ref"])
async def test_trusted_source_store_rejects_any_binding_change(tmp_path: Path, changed: str) -> None:
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"video")
    store = MediaKitTrustedSourceStore(tmp_path / "private-media")
    staged = await store.stage_local_video(
        user_id="user-1",
        project_id="project-1",
        source_path=source_path,
        rights_ref="rights-1",
    )
    values = {
        "user_id": "user-1",
        "project_id": "project-1",
        "local_task_id": "task-1",
        "source_ref": staged.source_ref,
        "rights_ref": "rights-1",
        "source_content_sha256": staged.content_sha256,
    }
    replacements = {
        "owner": ("user_id", "user-2"),
        "project": ("project_id", "project-2"),
        "rights": ("rights_ref", "rights-2"),
        "hash": ("source_content_sha256", "0" * 64),
        "source_ref": ("source_ref", "media-source:" + "1" * 64),
    }
    key, value = replacements[changed]
    values[key] = value

    with pytest.raises(MediaKitCommandError, match="trusted media source is unavailable"):
        await store.resolve(MediaKitCloudSourceContext(**values))


@pytest.mark.asyncio
async def test_trusted_source_store_detects_private_blob_tampering(tmp_path: Path) -> None:
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"original")
    store = MediaKitTrustedSourceStore(tmp_path / "private-media")
    staged = await store.stage_local_video(
        user_id="user-1",
        project_id="project-1",
        source_path=source_path,
        rights_ref="rights-1",
    )
    context = _source_context(
        source_ref=staged.source_ref,
        content_sha256=staged.content_sha256,
    )
    resolved = await store.resolve(context)
    Path(resolved.locator).chmod(0o600)
    Path(resolved.locator).write_bytes(b"tampered")

    with pytest.raises(MediaKitCommandError, match="source content verification failed"):
        await store.verify(context, resolved)

    malformed = MediaKitCloudSourceContext(
        user_id="user-1",
        project_id="project-1",
        local_task_id="task-1",
        source_ref=staged.source_ref,
        rights_ref="rights-1",
        source_content_sha256="../escape",
    )
    with pytest.raises(MediaKitCommandError, match="source content verification failed"):
        await store.verify(malformed, resolved)


@pytest.mark.asyncio
async def test_safe_downloader_streams_https_with_hash_and_no_url_in_result(tmp_path: Path) -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            headers={"Content-Type": "video/mp4", "Content-Length": "11"},
            content=b"video-bytes",
        )

    downloader = MediaKitSafeHttpDownloader(
        allowed_hosts={"media.example.com"},
        transport=httpx.MockTransport(handler),
        resolver=_public_resolver,
    )
    target = tmp_path / "download.part"
    downloaded = await downloader.download(
        "https://media.example.com/result.mp4?signature=secret",
        target,
        maximum_bytes=1024,
    )

    assert calls == ["https://media.example.com/result.mp4?signature=secret"]
    assert target.read_bytes() == b"video-bytes"
    assert downloaded.content_sha256 == hashlib.sha256(b"video-bytes").hexdigest()
    assert downloaded.size_bytes == 11
    assert downloaded.declared_content_type == "video/mp4"
    assert "signature" not in repr(downloaded)


@pytest.mark.asyncio
async def test_safe_downloader_rejects_private_redirect_and_removes_partial_file(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/internal"})

    downloader = MediaKitSafeHttpDownloader(
        allowed_hosts={"media.example.com", "127.0.0.1"},
        transport=httpx.MockTransport(handler),
        resolver=_public_resolver,
    )
    target = tmp_path / "download.part"

    with pytest.raises(MediaKitCommandError, match="result download URL is not allowed"):
        await downloader.download(
            "https://media.example.com/result.mp4",
            target,
            maximum_bytes=1024,
        )
    assert not target.exists()


@pytest.mark.asyncio
async def test_safe_downloader_enforces_declared_and_streamed_byte_limits(tmp_path: Path) -> None:
    async def declared_too_large(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "100"}, content=b"small")

    downloader = MediaKitSafeHttpDownloader(
        allowed_hosts={"media.example.com"},
        transport=httpx.MockTransport(declared_too_large),
        resolver=_public_resolver,
    )
    with pytest.raises(MediaKitCommandError, match="result exceeds its byte limit"):
        await downloader.download(
            "https://media.example.com/result.mp4",
            tmp_path / "declared.part",
            maximum_bytes=10,
        )

    async def streamed_too_large(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"01234567890")

    downloader = MediaKitSafeHttpDownloader(
        allowed_hosts={"media.example.com"},
        transport=httpx.MockTransport(streamed_too_large),
        resolver=_public_resolver,
    )
    target = tmp_path / "streamed.part"
    with pytest.raises(MediaKitCommandError, match="result exceeds its byte limit"):
        await downloader.download(
            "https://media.example.com/result.mp4",
            target,
            maximum_bytes=10,
        )
    assert not target.exists()


@pytest.mark.asyncio
async def test_result_materializer_downloads_checks_and_reuses_first_sealed_task_result(tmp_path: Path) -> None:
    downloads = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal downloads
        downloads += 1
        return httpx.Response(200, headers={"Content-Type": "application/octet-stream"}, content=b"valid-video")

    checked: list[bytes] = []

    async def quality_check(path: Path, policy: MediaKitCloudOutputPolicy, declared_content_type: str | None) -> str:
        checked.append(path.read_bytes())
        assert policy.media_kind == "video"
        assert declared_content_type == "application/octet-stream"
        return "video/mp4"

    downloader = MediaKitSafeHttpDownloader(
        allowed_hosts={"media.example.com"},
        transport=httpx.MockTransport(handler),
        resolver=_public_resolver,
    )
    materializer = MediaKitCloudResultMaterializer(
        root=tmp_path / "private-media",
        downloader=downloader,
        policies=(
            MediaKitCloudOutputPolicy(
                capability_domain="video",
                capability_tool="enhance-video",
                url_field="video_url",
                media_kind="video",
                maximum_bytes=1024,
            ),
        ),
        quality_check=quality_check,
    )
    first = await materializer(
        _materialization_context(
            provider_output={"status": "completed", "video_url": "https://media.example.com/one.mp4?sig=secret"},
        )
    )
    second = await materializer(
        _materialization_context(
            provider_output={"status": "completed", "video_url": "https://media.example.com/two.mp4?sig=rotated"},
            provider_output_sha256="9" * 64,
        )
    )

    assert first == second
    assert downloads == 1
    assert checked == [b"valid-video"]
    assert first.artifact_ref.startswith("artifact://mediakit/")
    assert first.content_sha256 == hashlib.sha256(b"valid-video").hexdigest()
    assert first.content_type == "video/mp4"
    receipt_paths = list((tmp_path / "private-media").rglob("receipt.json"))
    assert len(receipt_paths) == 1
    receipt_text = receipt_paths[0].read_text(encoding="utf-8")
    assert "https://" not in receipt_text
    assert "secret" not in receipt_text
    assert "remote-secret-task" not in receipt_text
    artifact_path = next((tmp_path / "private-media").rglob(f"{first.content_sha256}.media"))
    artifact_path.chmod(0o600)
    artifact_path.write_bytes(b"tampered")
    with pytest.raises(MediaKitCommandError, match="sealed result receipt is invalid"):
        await materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/three.mp4"},
            )
        )
    assert downloads == 1


@pytest.mark.asyncio
async def test_result_receipt_rejects_a_different_fee_quote_for_the_same_task(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"valid-video")

    async def quality_check(
        _path: Path,
        _policy: MediaKitCloudOutputPolicy,
        _declared_content_type: str | None,
    ) -> str:
        return "video/mp4"

    materializer = MediaKitCloudResultMaterializer(
        root=tmp_path / "private-media",
        downloader=MediaKitSafeHttpDownloader(
            allowed_hosts={"media.example.com"},
            transport=httpx.MockTransport(handler),
            resolver=_public_resolver,
        ),
        policies=(
            MediaKitCloudOutputPolicy(
                capability_domain="video",
                capability_tool="enhance-video",
                url_field="video_url",
                media_kind="video",
                maximum_bytes=1024,
            ),
        ),
        quality_check=quality_check,
    )
    await materializer(
        _materialization_context(
            provider_output={"video_url": "https://media.example.com/first.mp4"},
        )
    )

    with pytest.raises(MediaKitCommandError, match="sealed result receipt is invalid"):
        await materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/second.mp4"},
                fee_quote_sha256="7" * 64,
            )
        )


@pytest.mark.asyncio
async def test_result_materializer_rejects_unregistered_capability_before_download(tmp_path: Path) -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"unexpected")

    async def quality_check(_path: Path, _policy: MediaKitCloudOutputPolicy, _declared_content_type: str | None) -> str:
        return "video/mp4"

    materializer = MediaKitCloudResultMaterializer(
        root=tmp_path / "private-media",
        downloader=MediaKitSafeHttpDownloader(
            allowed_hosts={"media.example.com"},
            transport=httpx.MockTransport(handler),
            resolver=_public_resolver,
        ),
        policies=(),
        quality_check=quality_check,
    )

    with pytest.raises(MediaKitCommandError, match="output capability is not enabled"):
        await materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/result.mp4"},
            )
        )
    assert called is False


@pytest.mark.asyncio
async def test_result_materializer_does_not_seal_failed_quality_check(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-a-video")

    async def reject_quality(_path: Path, _policy: MediaKitCloudOutputPolicy, _declared_content_type: str | None) -> str:
        raise ValueError("decoder leaked signed-url-secret")

    materializer = MediaKitCloudResultMaterializer(
        root=tmp_path / "private-media",
        downloader=MediaKitSafeHttpDownloader(
            allowed_hosts={"media.example.com"},
            transport=httpx.MockTransport(handler),
            resolver=_public_resolver,
        ),
        policies=(
            MediaKitCloudOutputPolicy(
                capability_domain="video",
                capability_tool="enhance-video",
                url_field="video_url",
                media_kind="video",
                maximum_bytes=1024,
            ),
        ),
        quality_check=reject_quality,
    )

    with pytest.raises(MediaKitCommandError, match="result quality check failed") as caught:
        await materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/result.mp4?sig=secret"},
            )
        )
    assert "secret" not in str(caught.value)
    assert not list((tmp_path / "private-media").rglob("receipt.json"))


@pytest.mark.asyncio
async def test_result_materializer_rejects_malformed_quality_content_type(tmp_path: Path) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"video")

    async def malformed_quality_type(
        _path: Path,
        _policy: MediaKitCloudOutputPolicy,
        _declared_content_type: str | None,
    ) -> str:
        return "video/mp4\nx-private-path: /secret"

    materializer = MediaKitCloudResultMaterializer(
        root=tmp_path / "private-media",
        downloader=MediaKitSafeHttpDownloader(
            allowed_hosts={"media.example.com"},
            transport=httpx.MockTransport(handler),
            resolver=_public_resolver,
        ),
        policies=(
            MediaKitCloudOutputPolicy(
                capability_domain="video",
                capability_tool="enhance-video",
                url_field="video_url",
                media_kind="video",
                maximum_bytes=1024,
            ),
        ),
        quality_check=malformed_quality_type,
    )

    with pytest.raises(MediaKitCommandError, match="invalid content type") as caught:
        await materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/result.mp4"},
            )
        )
    assert "secret" not in str(caught.value)
    assert not list((tmp_path / "private-media").rglob("receipt.json"))


@pytest.mark.asyncio
async def test_concurrent_materializers_keep_the_first_atomically_sealed_result(tmp_path: Path) -> None:
    both_downloaded = asyncio.Event()
    download_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal download_count
        download_count += 1
        if download_count == 2:
            both_downloaded.set()
        await both_downloaded.wait()
        return httpx.Response(200, content=request.url.path.encode("utf-8"))

    async def quality_check(path: Path, _policy: MediaKitCloudOutputPolicy, _declared_content_type: str | None) -> str:
        assert path.read_bytes()
        return "video/mp4"

    materializer = MediaKitCloudResultMaterializer(
        root=tmp_path / "private-media",
        downloader=MediaKitSafeHttpDownloader(
            allowed_hosts={"media.example.com"},
            transport=httpx.MockTransport(handler),
            resolver=_public_resolver,
        ),
        policies=(
            MediaKitCloudOutputPolicy(
                capability_domain="video",
                capability_tool="enhance-video",
                url_field="video_url",
                media_kind="video",
                maximum_bytes=1024,
            ),
        ),
        quality_check=quality_check,
    )

    first, second = await asyncio.gather(
        materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/first.mp4"},
                provider_output_sha256="1" * 64,
            )
        ),
        materializer(
            _materialization_context(
                provider_output={"video_url": "https://media.example.com/second.mp4"},
                provider_output_sha256="2" * 64,
            )
        ),
    )

    assert first == second
    assert download_count == 2
    assert len(list((tmp_path / "private-media").rglob("receipt.json"))) == 1
    assert len(list((tmp_path / "private-media").rglob("*.media"))) == 1


@pytest.mark.asyncio
async def test_video_quality_checker_uses_local_mediakit_probe_and_narrow_stream_contract(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    async def runner(command: tuple[str, ...], _timeout_seconds: float) -> CommandResult:
        commands.append(command)
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "name": "probe_video_metadata",
                        "description": "probe",
                        "input_schema": {
                            "type": "object",
                            "properties": {"video_url": {"type": "string"}},
                            "required": ["video_url"],
                        },
                        "output_schema": {"type": "object"},
                    }
                ),
                stderr="",
            )
        return CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "format_meta": {"container": "mov,mp4,m4a,3gp,3g2,mj2", "duration": 1.0, "size": 12},
                    "video_stream_meta": {"codec": "h264", "duration": 1.0, "width": 320, "height": 240, "fps": 25.0},
                }
            ),
            stderr="",
        )

    path = tmp_path / "download.media"
    path.write_bytes(b"fake-video-bytes")
    policy = MediaKitCloudOutputPolicy(
        capability_domain="video",
        capability_tool="enhance-video",
        url_field="video_url",
        media_kind="video",
        maximum_bytes=1024,
    )
    checker = MediaKitVideoArtifactQualityChecker(MediaKitCapabilityRouter(runner=runner))

    content_type = await checker(path, policy, "application/octet-stream")

    assert content_type == "video/mp4"
    assert commands[-1] == (
        "mediakit-cli",
        "--local",
        "video",
        "probe-video-metadata",
        "--video-url",
        str(path),
    )


def test_output_policy_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="url_field"):
        MediaKitCloudOutputPolicy(
            capability_domain="video",
            capability_tool="enhance-video",
            url_field="arbitrary_url",
            media_kind="video",
            maximum_bytes=1024,
        )
    with pytest.raises(ValueError, match="must agree"):
        MediaKitCloudOutputPolicy(
            capability_domain="video",
            capability_tool="enhance-video",
            url_field="audio_url",
            media_kind="video",
            maximum_bytes=1024,
        )
