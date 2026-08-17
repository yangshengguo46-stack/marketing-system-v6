from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from deerflow.community.url_safety import resolve_host_addresses, validate_public_http_url
from deerflow.incubation.media import EphemeralMediaSource, VideoMetadataObservation

from .contracts import (
    MediaKitCloudMaterializationContext,
    MediaKitCloudMaterializedOutput,
    MediaKitCloudOutputPolicy,
    MediaKitCloudSourceContext,
)
from .router import MediaKitCapabilityRouter, MediaKitCommandError

AddressResolver = Callable[[str], list]
ArtifactQualityCheck = Callable[[Path, MediaKitCloudOutputPolicy, str | None], Awaitable[str]]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_TYPE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_SOURCE_CONTRACT_VERSION = "mediakit-private-source-v1"
_RESULT_CONTRACT_VERSION = "mediakit-private-result-v1"
_SOURCE_RESOLVER = "mediakit-private-content-store:v1"
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} characters")
    return normalized


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_reference(
    *,
    user_id: str,
    project_id: str,
    rights_ref: str,
    content_sha256: str,
) -> str:
    digest = _canonical_sha256(
        {
            "contract_version": _SOURCE_CONTRACT_VERSION,
            "user_id": user_id,
            "project_id": project_id,
            "rights_ref": rights_ref,
            "content_sha256": content_sha256,
            "media_kind": "video",
        }
    )
    return f"media-source:{digest}"


def _hash_regular_file(path: Path, *, maximum_bytes: int | None = None) -> tuple[str, int]:
    try:
        file_stat = path.lstat()
    except OSError:
        raise MediaKitCommandError("MediaKit source content verification failed") from None
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise MediaKitCommandError("MediaKit source content verification failed")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_DOWNLOAD_CHUNK_BYTES):
                size += len(chunk)
                if maximum_bytes is not None and size > maximum_bytes:
                    raise MediaKitCommandError("MediaKit source exceeds its byte limit")
                digest.update(chunk)
    except MediaKitCommandError:
        raise
    except OSError:
        raise MediaKitCommandError("MediaKit source content verification failed") from None
    return digest.hexdigest(), size


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        raise MediaKitCommandError("MediaKit private media directory is unavailable") from None


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _seal_private_json_once(path: Path, payload: bytes) -> bool:
    _private_directory(path.parent)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".part", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            return False
        return True
    finally:
        if fd >= 0:
            os.close(fd)
        _unlink_quietly(temporary_path)


def _read_private_text(path: Path) -> str | None:
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise MediaKitCommandError("MediaKit sealed result receipt is invalid") from None
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise MediaKitCommandError("MediaKit sealed result receipt is invalid")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        raise MediaKitCommandError("MediaKit sealed result receipt is invalid") from None


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitStagedSource:
    source_ref: str
    content_sha256: str
    size_bytes: int

    def __repr__(self) -> str:
        return f"MediaKitStagedSource(source_ref={self.source_ref!r}, content_sha256={self.content_sha256!r}, size_bytes={self.size_bytes!r})"


class MediaKitTrustedSourceStore:
    """Private, owner/project-scoped content store for exact MediaKit inputs."""

    def __init__(self, root: str | Path, *, maximum_source_bytes: int = 20 * 1024 * 1024 * 1024) -> None:
        if not isinstance(maximum_source_bytes, int) or isinstance(maximum_source_bytes, bool) or maximum_source_bytes <= 0:
            raise ValueError("maximum_source_bytes must be a positive integer")
        self._root = Path(root).expanduser().resolve()
        self._maximum_source_bytes = maximum_source_bytes

    def _source_dir(self, user_id: str, project_id: str) -> Path:
        return self._root / "sources" / _sha256_text(user_id) / _sha256_text(project_id)

    def _source_path(self, user_id: str, project_id: str, content_sha256: str) -> Path:
        return self._source_dir(user_id, project_id) / f"{content_sha256}.video"

    async def stage_local_video(
        self,
        *,
        user_id: str,
        project_id: str,
        source_path: str | Path,
        rights_ref: str,
    ) -> MediaKitStagedSource:
        owner = _bounded_text(user_id, name="user_id", maximum=64)
        project = _bounded_text(project_id, name="project_id", maximum=64)
        rights = _bounded_text(rights_ref, name="rights_ref", maximum=255)
        path = Path(source_path).expanduser()
        return await asyncio.to_thread(
            self._stage_local_video,
            owner,
            project,
            path,
            rights,
        )

    def _stage_local_video(
        self,
        user_id: str,
        project_id: str,
        source_path: Path,
        rights_ref: str,
    ) -> MediaKitStagedSource:
        try:
            source_stat = source_path.lstat()
        except OSError:
            raise MediaKitCommandError("MediaKit source staging failed") from None
        if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
            raise MediaKitCommandError("MediaKit source staging failed")

        source_dir = self._source_dir(user_id, project_id)
        _private_directory(source_dir)
        fd, temporary_name = tempfile.mkstemp(prefix=".source-", suffix=".part", dir=source_dir)
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        size = 0
        try:
            with source_path.open("rb") as source, os.fdopen(fd, "wb") as target:
                fd = -1
                while chunk := source.read(_DOWNLOAD_CHUNK_BYTES):
                    size += len(chunk)
                    if size > self._maximum_source_bytes:
                        raise MediaKitCommandError("MediaKit source exceeds its byte limit")
                    digest.update(chunk)
                    target.write(chunk)
                if size == 0:
                    raise MediaKitCommandError("MediaKit source cannot be empty")
                target.flush()
                os.fsync(target.fileno())
            content_sha256 = digest.hexdigest()
            destination = self._source_path(user_id, project_id, content_sha256)
            if destination.exists():
                stored_sha256, stored_size = _hash_regular_file(
                    destination,
                    maximum_bytes=self._maximum_source_bytes,
                )
                if stored_sha256 != content_sha256 or stored_size != size:
                    raise MediaKitCommandError("MediaKit private source store is inconsistent")
                _unlink_quietly(temporary_path)
            else:
                os.chmod(temporary_path, 0o400)
                os.replace(temporary_path, destination)
            return MediaKitStagedSource(
                source_ref=_source_reference(
                    user_id=user_id,
                    project_id=project_id,
                    rights_ref=rights_ref,
                    content_sha256=content_sha256,
                ),
                content_sha256=content_sha256,
                size_bytes=size,
            )
        finally:
            if fd >= 0:
                os.close(fd)
            _unlink_quietly(temporary_path)

    async def resolve(self, context: MediaKitCloudSourceContext) -> EphemeralMediaSource:
        try:
            user_id = _bounded_text(context.user_id, name="user_id", maximum=64)
            project_id = _bounded_text(context.project_id, name="project_id", maximum=64)
            source_ref = _bounded_text(context.source_ref, name="source_ref", maximum=255)
            rights_ref = _bounded_text(context.rights_ref, name="rights_ref", maximum=255)
            content_sha256 = _bounded_text(
                context.source_content_sha256,
                name="source_content_sha256",
                maximum=64,
            )
            if not _SHA256.fullmatch(content_sha256):
                raise ValueError("invalid content digest")
            expected_ref = _source_reference(
                user_id=user_id,
                project_id=project_id,
                rights_ref=rights_ref,
                content_sha256=content_sha256,
            )
            if source_ref != expected_ref:
                raise ValueError("source identity mismatch")
            path = self._source_path(user_id, project_id, content_sha256)
            file_stat = await asyncio.to_thread(path.lstat)
            if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
                raise ValueError("source is not a regular file")
            return await asyncio.to_thread(
                EphemeralMediaSource.local_file,
                source_ref=source_ref,
                locator=path,
                rights_ref=rights_ref,
                resolver=_SOURCE_RESOLVER,
            )
        except Exception:
            raise MediaKitCommandError("MediaKit trusted media source is unavailable") from None

    async def verify(
        self,
        context: MediaKitCloudSourceContext,
        source: EphemeralMediaSource,
    ) -> None:
        try:
            user_id = _bounded_text(context.user_id, name="user_id", maximum=64)
            project_id = _bounded_text(context.project_id, name="project_id", maximum=64)
            content_sha256 = _bounded_text(
                context.source_content_sha256,
                name="source_content_sha256",
                maximum=64,
            )
            if not _SHA256.fullmatch(content_sha256):
                raise ValueError("invalid content digest")
            if source.transport != "local_file":
                raise ValueError("trusted source is not local")
            if source.source_ref != context.source_ref or source.rights_ref != context.rights_ref or source.resolver != _SOURCE_RESOLVER:
                raise ValueError("trusted source identity mismatch")
            expected_path = self._source_path(
                user_id,
                project_id,
                content_sha256,
            )
            expected_path = await asyncio.to_thread(expected_path.resolve)
            actual_path = await asyncio.to_thread(Path(source.locator).resolve)
            if actual_path != expected_path:
                raise ValueError("trusted source path mismatch")
            actual_sha256, _ = await asyncio.to_thread(
                _hash_regular_file,
                expected_path,
                maximum_bytes=self._maximum_source_bytes,
            )
            if actual_sha256 != content_sha256:
                raise ValueError("trusted source content mismatch")
        except Exception:
            raise MediaKitCommandError("MediaKit source content verification failed") from None


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitDownloadedArtifact:
    content_sha256: str
    size_bytes: int
    declared_content_type: str | None

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a SHA-256 digest")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes <= 0:
            raise ValueError("size_bytes must be a positive integer")
        if self.declared_content_type is not None and (len(self.declared_content_type) > 128 or not _CONTENT_TYPE.fullmatch(self.declared_content_type)):
            raise ValueError("declared_content_type must be a bounded MIME type")

    def __repr__(self) -> str:
        return f"MediaKitDownloadedArtifact(content_sha256={self.content_sha256!r}, size_bytes={self.size_bytes!r}, declared_content_type={self.declared_content_type!r})"


class MediaKitSafeHttpDownloader:
    """Stream one provider result through allowlist, SSRF, and size guards."""

    def __init__(
        self,
        *,
        allowed_hosts: Collection[str],
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: AddressResolver = resolve_host_addresses,
        timeout_seconds: float = 120,
        maximum_redirects: int = 3,
    ) -> None:
        normalized_hosts = frozenset(host.strip().rstrip(".").casefold() for host in allowed_hosts if isinstance(host, str) and host.strip())
        if not normalized_hosts:
            raise ValueError("allowed_hosts must contain at least one host")
        if timeout_seconds <= 0 or maximum_redirects < 0:
            raise ValueError("download timeout and redirect limit are invalid")
        self._allowed_hosts = normalized_hosts
        self._transport = transport
        self._resolver = resolver
        self._timeout_seconds = timeout_seconds
        self._maximum_redirects = maximum_redirects

    def _host_is_allowed(self, hostname: str) -> bool:
        normalized = hostname.rstrip(".").casefold()
        return any(normalized == allowed or normalized.endswith(f".{allowed}") for allowed in self._allowed_hosts)

    async def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise MediaKitCommandError("MediaKit result download URL is not allowed")
        if parsed.hostname is None or not self._host_is_allowed(parsed.hostname):
            raise MediaKitCommandError("MediaKit result download URL is not allowed")
        error = await asyncio.to_thread(
            validate_public_http_url,
            url,
            action="download MediaKit result",
            resolver=self._resolver,
        )
        if error is not None:
            raise MediaKitCommandError("MediaKit result download URL is not allowed")

    async def download(
        self,
        url: str,
        target_path: str | Path,
        *,
        maximum_bytes: int,
    ) -> MediaKitDownloadedArtifact:
        if not isinstance(maximum_bytes, int) or isinstance(maximum_bytes, bool) or maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be a positive integer")
        target = Path(target_path)
        await asyncio.to_thread(_private_directory, target.parent)
        await asyncio.to_thread(_unlink_quietly, target)
        current_url = _bounded_text(url, name="download URL", maximum=8192)
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
                timeout=self._timeout_seconds,
            ) as client:
                for redirect_count in range(self._maximum_redirects + 1):
                    await self._validate_url(current_url)
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location or redirect_count >= self._maximum_redirects:
                                raise MediaKitCommandError("MediaKit result download redirect was rejected")
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code != 200:
                            raise MediaKitCommandError("MediaKit result download failed")
                        content_length = response.headers.get("Content-Length")
                        if content_length is not None:
                            try:
                                declared_size = int(content_length)
                            except ValueError:
                                raise MediaKitCommandError("MediaKit result download returned an invalid size") from None
                            if declared_size < 0 or declared_size > maximum_bytes:
                                raise MediaKitCommandError("MediaKit result exceeds its byte limit")

                        digest = hashlib.sha256()
                        size = 0
                        handle = await asyncio.to_thread(target.open, "xb")
                        try:
                            async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK_BYTES):
                                size += len(chunk)
                                if size > maximum_bytes:
                                    raise MediaKitCommandError("MediaKit result exceeds its byte limit")
                                digest.update(chunk)
                                await asyncio.to_thread(handle.write, chunk)
                            if size == 0:
                                raise MediaKitCommandError("MediaKit result download was empty")
                            await asyncio.to_thread(handle.flush)
                            await asyncio.to_thread(os.fsync, handle.fileno())
                        finally:
                            await asyncio.to_thread(handle.close)
                        content_type = response.headers.get("Content-Type")
                        declared_content_type = None
                        if content_type:
                            candidate = content_type.split(";", maxsplit=1)[0].strip().casefold()
                            if candidate and len(candidate) <= 128 and _CONTENT_TYPE.fullmatch(candidate):
                                declared_content_type = candidate
                        return MediaKitDownloadedArtifact(
                            content_sha256=digest.hexdigest(),
                            size_bytes=size,
                            declared_content_type=declared_content_type,
                        )
            raise MediaKitCommandError("MediaKit result download redirect was rejected")
        except MediaKitCommandError:
            await asyncio.to_thread(_unlink_quietly, target)
            raise
        except Exception:
            await asyncio.to_thread(_unlink_quietly, target)
            raise MediaKitCommandError("MediaKit result download failed") from None


class MediaKitCloudResultMaterializer:
    """Seal one enabled cloud file result without retaining its provider URL."""

    def __init__(
        self,
        *,
        root: str | Path,
        downloader: MediaKitSafeHttpDownloader,
        policies: Collection[MediaKitCloudOutputPolicy],
        quality_check: ArtifactQualityCheck,
    ) -> None:
        self._root = Path(root).expanduser().resolve()
        self._downloader = downloader
        self._quality_check = quality_check
        self._policies: dict[tuple[str, str], MediaKitCloudOutputPolicy] = {}
        for policy in policies:
            key = (policy.capability_domain, policy.capability_tool)
            if key in self._policies:
                raise ValueError("MediaKit output policies must be unique per capability")
            self._policies[key] = policy

    def _task_dir(self, context: MediaKitCloudMaterializationContext) -> Path:
        return self._root / "results" / _sha256_text(context.user_id) / _sha256_text(context.local_task_id)

    @staticmethod
    def _receipt_identity(context: MediaKitCloudMaterializationContext) -> dict[str, object]:
        return {
            "contract_version": _RESULT_CONTRACT_VERSION,
            "project_id_sha256": _sha256_text(context.project_id),
            "remote_task_id_sha256": _sha256_text(context.remote_task_id),
            "source_ref_sha256": _sha256_text(context.source_ref),
            "source_content_sha256": context.source_content_sha256,
            "capability_domain": context.capability_domain,
            "capability_tool": context.capability_tool,
            "operation_sha256": context.operation_sha256,
        }

    async def _reuse_receipt(
        self,
        context: MediaKitCloudMaterializationContext,
        receipt_path: Path,
    ) -> MediaKitCloudMaterializedOutput | None:
        try:
            payload = await asyncio.to_thread(_read_private_text, receipt_path)
            if payload is None:
                return None
            record = json.loads(payload)
            if not isinstance(record, dict):
                raise ValueError("invalid receipt")
            expected_identity = self._receipt_identity(context)
            if any(record.get(key) != value for key, value in expected_identity.items()):
                raise ValueError("receipt identity mismatch")
            output = MediaKitCloudMaterializedOutput(
                artifact_ref=record["artifact_ref"],
                content_sha256=record["content_sha256"],
                content_type=record["content_type"],
                size_bytes=record["size_bytes"],
            )
            artifact_path = self._task_dir(context) / f"{output.content_sha256}.media"
            actual_sha256, actual_size = await asyncio.to_thread(_hash_regular_file, artifact_path)
            if actual_sha256 != output.content_sha256 or actual_size != output.size_bytes:
                raise ValueError("sealed artifact changed")
            return output
        except Exception:
            raise MediaKitCommandError("MediaKit sealed result receipt is invalid") from None

    async def __call__(
        self,
        context: MediaKitCloudMaterializationContext,
    ) -> MediaKitCloudMaterializedOutput:
        policy = self._policies.get((context.capability_domain, context.capability_tool))
        if policy is None:
            raise MediaKitCommandError("MediaKit output capability is not enabled")
        task_dir = self._task_dir(context)
        await asyncio.to_thread(_private_directory, task_dir)
        receipt_path = task_dir / "receipt.json"
        reused = await self._reuse_receipt(context, receipt_path)
        if reused is not None:
            return reused

        output_url = context.provider_output.get(policy.url_field)
        if not isinstance(output_url, str) or not output_url.strip():
            raise MediaKitCommandError("MediaKit completed result omitted its enabled output")
        temporary_path = task_dir / f".download-{os.urandom(12).hex()}.part"
        try:
            downloaded = await self._downloader.download(
                output_url,
                temporary_path,
                maximum_bytes=policy.maximum_bytes,
            )
            try:
                content_type = await self._quality_check(
                    temporary_path,
                    policy,
                    downloaded.declared_content_type,
                )
            except Exception:
                raise MediaKitCommandError("MediaKit result quality check failed") from None
            try:
                normalized_content_type = _bounded_text(
                    content_type,
                    name="quality content_type",
                    maximum=128,
                ).casefold()
            except ValueError:
                raise MediaKitCommandError("MediaKit result quality check returned an invalid content type") from None
            if not _CONTENT_TYPE.fullmatch(normalized_content_type) or not normalized_content_type.startswith(f"{policy.media_kind}/"):
                raise MediaKitCommandError("MediaKit result quality check returned an invalid content type")

            artifact_path = task_dir / f"{downloaded.content_sha256}.media"
            if await asyncio.to_thread(artifact_path.exists):
                actual_sha256, actual_size = await asyncio.to_thread(_hash_regular_file, artifact_path)
                if actual_sha256 != downloaded.content_sha256 or actual_size != downloaded.size_bytes:
                    raise MediaKitCommandError("MediaKit private result store is inconsistent")
                await asyncio.to_thread(_unlink_quietly, temporary_path)
            else:
                await asyncio.to_thread(os.chmod, temporary_path, 0o400)
                await asyncio.to_thread(os.replace, temporary_path, artifact_path)

            owner_token = _sha256_text(context.user_id)
            task_token = _sha256_text(context.local_task_id)
            artifact_ref = f"artifact://mediakit/{owner_token}/{task_token}/{downloaded.content_sha256}"
            output = MediaKitCloudMaterializedOutput(
                artifact_ref=artifact_ref,
                content_sha256=downloaded.content_sha256,
                content_type=normalized_content_type,
                size_bytes=downloaded.size_bytes,
            )
            record = {
                **self._receipt_identity(context),
                "sealed_provider_output_sha256": context.provider_output_sha256,
                **output.as_result(),
            }
            encoded = json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            sealed = await asyncio.to_thread(
                _seal_private_json_once,
                receipt_path,
                encoded,
            )
            if sealed:
                return output
            winner = await self._reuse_receipt(context, receipt_path)
            if winner is None:
                raise MediaKitCommandError("MediaKit sealed result receipt is invalid")
            if winner.content_sha256 != output.content_sha256:
                await asyncio.to_thread(_unlink_quietly, artifact_path)
            return winner
        finally:
            await asyncio.to_thread(_unlink_quietly, temporary_path)


class MediaKitVideoArtifactQualityChecker:
    """Use MediaKit's local probe plus a narrow metadata contract as video QC."""

    def __init__(self, router: MediaKitCapabilityRouter) -> None:
        self._router = router

    async def __call__(
        self,
        path: Path,
        policy: MediaKitCloudOutputPolicy,
        declared_content_type: str | None,
    ) -> str:
        if policy.media_kind != "video":
            raise ValueError("the video quality checker only accepts video output")
        source = await asyncio.to_thread(
            EphemeralMediaSource.local_file,
            source_ref=f"quality-check:{_sha256_text(str(path))}",
            locator=path,
            rights_ref="internal:mediakit-provider-output",
            resolver="mediakit-result-quality-check:v1",
        )
        prepared = await self._router.prepare_video_call(
            domain="video",
            tool="probe-video-metadata",
            source=source,
            mode="local",
        )
        execution = await self._router.execute_local(prepared)
        observation = VideoMetadataObservation.from_mediakit_output(execution.output)
        if observation.video_stream_meta is None:
            raise ValueError("downloaded result has no video stream")
        if declared_content_type is not None and declared_content_type.startswith("video/"):
            return declared_content_type
        container = observation.format_meta.container.casefold()
        if "webm" in container:
            return "video/webm"
        if "matroska" in container:
            return "video/x-matroska"
        if "avi" in container:
            return "video/x-msvideo"
        if "mpegts" in container or "mpeg-ts" in container:
            return "video/mp2t"
        return "video/mp4"


__all__ = [
    "ArtifactQualityCheck",
    "MediaKitCloudResultMaterializer",
    "MediaKitDownloadedArtifact",
    "MediaKitSafeHttpDownloader",
    "MediaKitStagedSource",
    "MediaKitTrustedSourceStore",
    "MediaKitVideoArtifactQualityChecker",
]
