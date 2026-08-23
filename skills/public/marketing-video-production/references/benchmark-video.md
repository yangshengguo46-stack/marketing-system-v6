# Benchmark-video Evidence and Transfer

A user-supplied benchmark video is evidence for learning structure, not a
template to clone. Store only bounded, provenance-aware observations and
project-native interpretations.

## Three Separate Layers

### 1. Observation

Record only what the source or deterministic tools support:

- duration, dimensions, frame rate, audio/video presence;
- sampled time ranges and coverage limitations;
- visible cut boundaries, shot-duration distribution, and transition types;
- visible text timing/density and spoken-word timing when OCR/ASR actually ran;
- sound events and silence only when observed;
- source hash, tool/schema version, and rights status.

Metadata proves metadata. A cut detector proves its reported boundaries, not
why the creator cut there. Missing OCR/ASR/scene runs remain missing.

### 2. Interpretation

Label inferred functions explicitly, for example:

- the opening likely creates an information gap;
- a reaction shot may make the claim easier to trust;
- text may carry context while the image demonstrates action;
- the ending may convert attention into one concrete next step.

Interpretations need observation references and confidence/limitations. They
must not be written back as source facts.

### 3. Transfer

Create an abstract pattern that can be executed with original content:

- hook window, information order, reveal timing;
- shot-duration bands rather than copied timecodes;
- action/reaction or problem/evidence/payoff relationships;
- text, voice, practical sound, silence, and music roles;
- transition logic and ending action.

Bind every transferred beat to the new `AdaptedDraft` and `ProductionPlan`.
When the benchmark's mechanism depends on the original creator's identity,
voice, access, trademark, copyrighted footage, or unrepeatable proof, mark it
`not_transferable`.

## Remake Safety

Do not promise pixel-level reproduction. Do not reuse frames, watermark,
signature phrases, logos, soundtrack, likeness, voice, or distinctive trade
dress without an independent reviewed right. A public URL or user upload proves
access, not permission to publish derivatives.

The desired output is “same useful grammar, new truthful execution,” not “make
the audience believe this came from the benchmark creator.”

## Coverage Receipt

Every sealed `BenchmarkVideoEvidence` must include one typed `coverage` receipt:

- `sampling_method`: how the source was sampled or probed;
- `analyzed_ranges`: non-overlapping source-time ranges actually analyzed;
- `capability_versions`: the exact domain, tool, version, and Schema hash from
  the `media_observation` execution receipt;
- `excluded_or_failed_ranges`: explicit ranges, outcome, and reason; an empty
  list means none were reported, not that every modality ran;
- `modalities_available`: exactly one status and basis/limitation for each of
  `technical_metadata`, `speech`, `on_screen_text`, `scene_structure`, `sound`,
  and `visual_framing`. Status is `observed`, `partially_observed`, `not_run`,
  `unavailable`, or `failed`;
- `observation_count`: the exact number of machine observations;
- `allowed_use`: either `analysis_only` or
  `analysis_and_abstract_structure_transfer`.

Capability versions must match the exact observation parent. Coverage ranges
cannot exceed its observed source duration, and a machine observation with a
time range must fall within `analyzed_ranges`. A modality cannot be marked
observed without a corresponding machine observation. With the current
metadata-only parent, speech, text, scene, sound, and frame-level visual
analysis remain `not_run` or otherwise unavailable.

`analysis_only` forbids routing identified patterns into a downstream
`ProductionPlan`. `analysis_and_abstract_structure_transfer` permits only the
already-fixed `abstract_structure_only` scope; it does not permit copied frames,
voice, identity, trade dress, soundtrack, or other derivative reuse.

`source.rights_ref` is always accompanied by
`rights_basis_status=declared_reference_not_verified`. It is a user/operator
declaration or provenance reference, not evidence that DeerFlow verified any
permission. Neither allowed-use value upgrades that declaration into a rights
clearance. Keep unresolved permission in `unknowns`/`limitations` and stop
before production when an independent reviewed right is required.
