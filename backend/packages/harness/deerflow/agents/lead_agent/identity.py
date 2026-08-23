from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files

IDENTITY_RESOURCE = "IDENTITY.md"
IDENTITY_SOURCE = "package://deerflow/agents/lead_agent/IDENTITY.md"
IDENTITY_MAX_UTF8_BYTES = 1_600


class ProductIdentityError(RuntimeError):
    """Raised when the committed default product identity is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ProductIdentityAsset:
    content: str
    source: str
    sha256: str
    version: str


def build_product_identity_asset(content: str, *, source: str) -> ProductIdentityAsset:
    normalized = content.rstrip() + "\n"
    if not normalized.strip():
        raise ProductIdentityError("product identity is empty")
    if normalized.count("<agent_kernel>") != 1 or normalized.count("</agent_kernel>") != 1:
        raise ProductIdentityError("product identity must contain exactly one <agent_kernel> block")
    if normalized.count("{agent_name}") != 1:
        raise ProductIdentityError("product identity must contain exactly one {agent_name} placeholder")
    if len(normalized.encode("utf-8")) > IDENTITY_MAX_UTF8_BYTES:
        raise ProductIdentityError(f"product identity exceeds {IDENTITY_MAX_UTF8_BYTES} UTF-8 bytes")

    digest = sha256(normalized.encode("utf-8")).hexdigest()
    return ProductIdentityAsset(
        content=normalized,
        source=source,
        sha256=digest,
        version=f"sha256:{digest}",
    )


def load_product_identity_asset() -> ProductIdentityAsset:
    resource = files(__package__).joinpath(IDENTITY_RESOURCE)
    try:
        content = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ProductIdentityError(f"default product identity resource is unavailable: {IDENTITY_RESOURCE}") from exc
    return build_product_identity_asset(content, source=IDENTITY_SOURCE)


PRODUCT_IDENTITY_ASSET = load_product_identity_asset()
