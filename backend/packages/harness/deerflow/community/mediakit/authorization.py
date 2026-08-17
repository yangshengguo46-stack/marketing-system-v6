from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from deerflow.incubation.contracts import ProjectRef
from deerflow.persistence.incubation_ledger import IncubationLedgerRepository

from .contracts import MediaKitCloudAuthorizationContext


class MediaKitCloudApprovalAuthorizer:
    """Bind an exact approved MediaKit operation to one durable local task."""

    def __init__(
        self,
        repository: IncubationLedgerRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    async def __call__(self, context: MediaKitCloudAuthorizationContext) -> None:
        await self._repository.authorize_approval_pair(
            project=ProjectRef(
                owner_user_id=context.user_id,
                project_id=context.project_id,
            ),
            cloud_processing_grant_id=context.cloud_processing_approval_ref,
            fee_authorization_grant_id=context.fee_authorization_ref,
            operation_sha256=context.operation_sha256,
            local_task_id=context.local_task_id,
            currency=context.currency,
            maximum_amount_micros=context.maximum_amount_micros,
            now=self._clock(),
        )


__all__ = ["MediaKitCloudApprovalAuthorizer"]
