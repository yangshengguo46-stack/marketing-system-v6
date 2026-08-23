# Project-native Video Pipeline

## Ownership

The Lead owns convergence and user interaction. Durable artifacts own state.
MediaKit, Ark, renderers, and director methods are workers below that boundary.

> confirmed account direction (optional context)
> → one evidenced topic → MessagePlan → BaseDraft
> → explicit FormatDecision → AdaptedDraft → explicit ProductionPlan
> → asset evidence, capture, or generation → assembly and QC
> → MediaArtifact → optional publication preview and approval

Do not merge these stages. In particular:

- an `AccountLaunchPlan` proposes operating rhythm and topic seeds;
- a `TopicBrief` owns evidence and the premise for one topic;
- an `AdaptedDraft` owns the selected presentation's sealed content; user intent
  to continue production is a separate explicit request;
- a `ProductionPlan` owns assets, production actions, and assembly steps;
- a `MediaArtifact` owns stable output identity, input bindings, execution
  receipt, and QC.

## Production-plan Gate

Use the existing V6 `ProductionPlan`; do not create a second video-plan schema or
JSON ledger. Before execution, verify:

1. the exact `AdaptedDraft` and `FormatDecision` parents;
2. the adapted-body SHA-256 and selected format;
3. each asset's source and purpose;
4. every `existing_user_material` basis artifact;
5. the action IDs, asset IDs, and assembly step IDs for this operation;
6. rights, resource gaps, unknowns, and limitations.

`provisional` means the plan still has unresolved execution inputs. A plan does
not become `ready` merely because a model filled every field.

## Asset Routing

- `existing_user_material`: use only the exact reviewed media-observation
  parent and recheck the source hash before execution.
- `to_capture` / `to_record`: return an executable capture brief; absence of
  footage is a gap, not permission to synthesize it.
- `to_create`: choose deterministic graphics or a sealed provider request from
  the action and asset purpose.
- `derived_from_adapted_draft`: text graphics and subtitles may reproduce only
  the exact sealed adapted content.

Route per asset. A hybrid video does not need a separate global orchestration
mode.

## Assembly and Closeout

Assembly consumes only plan-bound inputs. Preserve source and output hashes,
tool/schema versions, exact arguments digest, private storage reference, media
metadata, and QC. Temporary download URLs and local paths remain execution-only.

Finish with one of these truthful presentation labels (they are not the durable
task database enum):

- `planned`: reviewable plan only;
- `awaiting_approval`: paid or rights-sensitive execution is sealed but blocked;
- `running`: a durable task exists and may be polled;
- `submission_unknown`: provider acceptance is ambiguous; reconciliation needed;
- `produced`: content-addressed output and QC receipt exist;
- `blocked`: exact missing input or failed check is named.
