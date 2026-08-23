# Provider, Cost, and Material Boundaries

## MediaKit

MediaKit is the media capability and evidence layer. Use its dynamically
discovered schema and trusted private I/O. The currently accepted V6 vertical is
local MediaKit editing tool **trim-video** bound to exact `ProductionPlan` IDs and sealed as a
`MediaArtifact`; local metadata probing has also been live-smoked on MediaKit
CLI 0.2.0.

For every operation:

1. bind the exact production plan, action, assembly step, assets, schema hash,
   and arguments digest;
2. verify source bytes before execution;
3. execute into an isolated private attempt directory;
4. reject path escape, unexpected output types, and source mutation;
5. hash and probe the result, run capability-specific QC, then materialize an
   stable internal artifact reference.

Cloud ASR, OCR, scene analysis, and enhancement are not implied by local tool
availability. They require their own evidence contracts, quote, approvals,
durable task, private materialization, and live acceptance.

## Volcengine Ark: Future Registered Continuation

Ark image/video generation is not currently callable from this Skill. The
following is the registration target, not an available tool path:

> sealed plan-bound request
> → server-owned authentication, resource, model, and parameter preflight
> → freeze the exact selected model and reconciliation metadata
> → current quote and expiry
> → rights, cloud-processing, and fee authorization
> → at-most-once durable intent → persist cost marker → ArkCLI submission once
> → persist provider task ID → poll terminal state
> → private materialization and QC

The implemented V1 contract covers text-to-video only; Ark image generation,
reference images, and multi-shot continuity remain unimplemented. A future
ArkCLI driver should follow its own profile contract: verify authentication,
resolve configured resources, inspect supported parameters for public models,
then submit. Credentials come only from the local profile and never enter
arguments, prompts, receipts, or model context.

Video is fire-and-poll. `queued` and `running` mean the provider accepted the
task. A terminal provider failure is recorded without silently purchasing a
replacement.

## At-most-once Submission

ArkCLI does not currently expose an audited generation idempotency key. The
durable task must therefore use an at-most-once policy:

- persist the submission intent before any provider mutation;
- complete retry-safe authentication, resource, exact-model, and parameter
  preflight before setting the cost-incurring `submission_started_at` marker;
- after that marker, enter the provider's generation submission code only once;
- allow a recovery worker to claim an expired marked row only to seal the
  unknown outcome, never to call generation again;
- if the provider returns a task ID, persist it and poll normally;
- if certainty is lost after the call begins, seal `submission_unknown`;
- treat `submission_unknown` as terminal, attention-required, and
  non-claimable; never auto-resubmit it;
- require explicit reconciliation and a new, separately authorized replacement
  if the original task cannot be found.

This differs from providers that accept a durable client token and can safely
retry an idempotent submission.

## Ark Registration Hard Gates

Do not register the Ark driver or expose a Gateway continuation until all of
these conditions are enforced and tested:

1. The driver registration mechanically requires `at_most_once`; callers
   cannot omit the policy or route Ark through the legacy remote-first
   `submit()` method.
2. Retry-safe preflight finishes before the cost marker, and the exact selected
   profile/account/tenant/project/region plus selected public model or resolved
   Endpoint identity are frozen before quote, approvals, and provider submission.
   The request hash already requires explicit ratio, resolution, and duration;
   provider defaults cannot replace them.
3. The submission lease covers the paid call or is safely refreshed without
   reopening the submission boundary. A deterministic two-worker expiry test
   must show that recovery cannot create a second `+gen` call or discard the
   only reconcilable task identity.
4. Non-secret durable `driver_data` contains the exact `operation_sha256` and
   selected model before submission, and retains both in
   `submission_unknown` for reconciliation.
5. Driver submit and poll snapshots may contain only remote lifecycle states;
   local-only `submission_pending` and `submission_unknown` are rejected at the
   driver boundary.
6. Driver registration accepts only structured, redacted errors; arbitrary
   exception text cannot enter durable rows.
7. The concrete runner is shell-free argv execution with audited timeouts and
   output limits, and ArkCLI/SDK mutation retries are explicitly audited. A
   single CLI process is not assumed to equal one HTTP mutation.

## Material Discovery Is Not Rights Clearance

Search can find candidate footage, images, music, and source pages. It does not
turn them into plan assets. Before acquisition or use, record ownership,
license, consent, public-domain basis, attribution/share-alike obligations,
territory, duration, and transformation limits as applicable.

The fourth-version material-search work may be reused only after auditing its
provider terms, URL expiry, downloader behavior, content hashes, license
filters, and provenance receipts. The yt-dlp downloader, a browser, or a direct media URL is
transport—not a rights oracle.

## Registration Status

Contracts and adapters may exist before they are exposed to the Lead. Until the
Gateway continuation, exact approval service, durable driver registration, and
fresh live acceptance are complete, do not call Ark generation or cloud
MediaKit on the user's behalf. Report `implemented but unregistered` or
`not live-verified` precisely.

Unregistered means there is no dedicated Tool, Gateway, runner, or durable Ark
driver. It is not a host-level proof that an agent with generic Bash could never
invoke an installed CLI. Production rollout must also enforce the provider
mutation boundary technically; Skill prose alone is not that control.
