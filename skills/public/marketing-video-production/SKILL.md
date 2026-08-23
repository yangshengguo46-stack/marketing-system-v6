---
name: marketing-video-production
description: >-
  Plan and review the explicit downstream video-production continuation for the
  marketing agent. Use when an exact sealed AdaptedDraft exists and the user
  explicitly asks to continue into video production, or for user-supplied 对标视频
  decomposition, 分镜/生图/生视频/素材剪辑, or MediaKit/Volcengine Ark
  routing. Current Ark execution is unregistered: this skill must stop at a
  reviewable plan or awaiting-approval boundary and never call a paid provider.
---

# Marketing Video Production

> Current runtime boundary: this Skill can route, plan, review benchmark
> evidence, and prepare provider-safe requests. Ark image/video submission,
> download, materialization, and multi-shot assembly are not registered. Do not
> simulate those capabilities or call a provider from shell.

This is the project-native routing skill below the content brain. After an
exact `AdaptedDraft + FormatDecision` is sealed and the user explicitly asks to
continue into video production, it reviews or prepares the existing
`ProductionPlan` and its evidence/asset handoffs. Only already-registered local
operations may currently execute; generation, broad assembly, and the resulting
`MediaArtifact` remain future continuations unless an exact accepted vertical is
available. This Skill is not a second orchestrator and must not reopen account
direction, topic selection, factual claims, or monetization.

## Load Only What This Turn Needs

- End-to-end routing or a script handoff: read
  [pipeline.md](references/pipeline.md).
- A user-supplied benchmark video: also read
  [benchmark-video.md](references/benchmark-video.md).
- Shot design or a reviewable board: also read
  [director-craft.md](references/director-craft.md).
- MediaKit, Ark, cost, polling, or material sourcing: also read
  [provider-boundaries.md](references/provider-boundaries.md).

## Entry Boundary

Start only when the user explicitly asks to continue from content into
presentation or production. Prefer exact existing artifact receipts:

> AccountDirectionVersion (optional account context)
> → TopicBrief → MessagePlan → BaseDraft
> → FormatDecision → AdaptedDraft
> → ProductionPlan → media operations → MediaArtifact

An `AccountLaunchPlan` can nominate a topic seed, but it is not a script and
cannot skip evidence research, `TopicBrief`, or the content chain. If the user
has only chosen an account direction or topic, return to the Lead for the
missing upstream artifact instead of inventing a video.

## Choose One Primary Route

| Request | Primary route | Typical execution |
|---|---|---|
| 对标视频拆解并迁移结构 | `benchmark_transfer` | Observe locally, abstract a pattern, create original shots |
| 用用户已有素材剪成片 | `material_edit` | Bound user material, MediaKit/local edit, graphics |
| 需要生图或生视频补镜头 | `generated_assets` | Plan-bound provider requests; Ark execution is not yet registered |
| 口播重剪或素材插入 | `talking_head_edit` | Existing footage, inserts, captions, sound |
| 数据、界面或概念动效 | `motion_graphics` | Deterministic graphics renderer and finishing |
| 多种来源混用 | `hybrid` | Route each plan asset independently |

The route is an editorial decision, not a new durable schema. The existing
`ProductionPlan` remains authoritative.

## Workflow

1. Resolve the exact sealed content, format decision, adapted draft, the user's
   explicit request to continue into production, target platform,
   duration/ratio, available user materials, the user's rights declaration or
   provenance reference (not verified clearance), and
   unresolved gaps. Preserve unknowns.
2. If a benchmark video is supplied, require bounded machine evidence first.
   If no registered analysis path has produced it, stop with the missing
   evidence contract; do not simulate MediaKit ASR/OCR/scene analysis.
   Keep observation, interpretation, and transferable pattern separate. A
   benchmark grants neither reuse rights nor permission to copy identity.
3. Review or generate the existing `ProductionPlan`. Every asset, production
   action, and assembly step must bind to that plan; user material must retain
   its exact `user_material` parent.
4. Apply director craft only where it makes a shot more executable. Show a
   compact shot board for review, but do not parse the board back into state or
   create a parallel shot ledger.
5. Resolve each required asset as user-owned footage, material to capture,
   deterministic graphics, or a provider-generation request with exact cost,
   content, and execution approvals. Search
   results are discovery evidence until a separate rights declaration or
   provenance reference is recorded; that record is not rights verification.
6. Before any paid generation, show what would be generated, the exact plan
   binding, rights declaration/reference, and unresolved quote/approval requirements. In the
   current runtime, stop as `awaiting_approval`; no Ark Gateway execution path
   exists yet.
7. After a future registered continuation passes the gates below, treat video
   generation as fire-and-poll and reuse the durable task receipt. Queued or
   running is not failure. Never replace an ambiguous submission automatically.
8. Only that future registered continuation may privately materialize outputs,
   run MediaKit/local metadata and QC, assemble plan-bound assets, and seal a
   content-addressed `MediaArtifact`.
9. Present the result and its limitations. Publication, metrics, and account
   learning are separate explicit continuations.

## Hard Boundaries

- Do not change sealed dialogue, offers, product behavior, factual claims, or
  account direction. Request a new upstream revision if meaning must change.
- Do not call a paid provider directly from prose or shell. Provider execution
  requires a sealed request, current quote, exact approvals, and a durable task.
- An at-most-once task with `submission_pending + submission_started_at`, or in
  `submission_unknown`, is a cost fence. Reconcile it; never auto-retry it.
- Never place credentials, local paths, temporary URLs, cookies, raw provider
  output, or unrestricted parameter dictionaries in model-visible artifacts.
- Do not describe public search footage as usable material without ownership,
  license, consent, or a reviewed public-domain basis.
- Transfer timing and information grammar, not a creator's likeness, voice,
  watermark, copyrighted frames, signature trade dress, or misleading identity.
- Do not claim MediaKit metadata, ASR, OCR, or scene cuts prove creative intent.

## Current Implementation Boundary

The V6 codebase already owns `ProductionPlan`, private MediaKit I/O, the first
local trim-to-`MediaArtifact` vertical, durable tasks, and generic/MediaKit
approval primitives. The Ark single-shot and benchmark-video contracts are a safety
foundation until they are registered behind a Gateway continuation and pass a
fresh live run with exact user authorization. Do not bypass that gap with the generic
`video-generation` script or a direct `arkcli +gen` call.

Automatic ASR/OCR/scene decomposition, broad timeline assembly, audio/caption
mixing, whole-web rights-aware acquisition, and multi-shot generation remain
later slices. State these gaps rather than simulating success.
