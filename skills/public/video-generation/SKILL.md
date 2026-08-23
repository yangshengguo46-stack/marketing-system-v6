---
name: video-generation
description: >-
  Disabled legacy compatibility package. Do not activate it for video work: its
  historical Gemini/MiniMax helper bypasses V6 project lineage, quote and fee
  approval, durable-task recovery, and media provenance. Use
  marketing-video-production for every new video request.
---

# Disabled Legacy Video Generator

This package is retained only so old installations and script-level regression
tests can be understood during migration. It is disabled in the project
extensions configuration and is not an executable workflow for the Agent.

Do not run `scripts/generate.py` on a user's behalf. That historical helper can
submit paid Gemini or MiniMax requests directly and has no V6 `ProductionPlan`,
quote, exact approval, at-most-once task, private materialization, or provenance
boundary.

Route every new request—including isolated clips, benchmark remakes, generated
inserts, and reference-frame work—to `marketing-video-production`. Until that
Skill's Gateway continuation is registered and live-accepted, return a plan or
`awaiting_approval` boundary rather than making a provider call.
