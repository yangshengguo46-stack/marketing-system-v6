---
name: incubate-food-world
description: >-
  Shadow candidate for account incubation when the user's commercial object is
  a complete food category, ingredient category, or an intermediate product
  whose primary role is to complete a named food or drink. Compares the sold
  object, completed food world, seller operation, eating scene, and social
  function without merging them. Do not use for cookware, nutrition consulting,
  restaurant operations, or a venue business unless food itself is the stated
  long-term content subject.
license: MIT
compatibility: DeerFlow v6 incubation profile lab only; not in the runtime Skill registry
metadata:
  author: DeerFlow v6 content-intelligence project
  version: "0.1.0"
  lifecycle: shadow
  source: docs/content-intelligence-v6/audits/A117-open-source-domain-skill-architecture.md
---

# Food World Incubation Shadow Candidate

This candidate tests one reusable distinction. It does not contain answers for
individual products and must not enter the public Skill registry before held-out
and repeated-run acceptance.

## Boundary

1. Preserve the user's exact commercial expression.
2. Compare a complete food category with seller operations and eating scenes.
3. When the sold object is an intermediate carrier, compare it with the named
   food or drink it exists to complete.
4. Select one minimal complete content root. Do not join a product, an eating
   scene, and a social function into a hybrid root.
5. Keep region, production, purchase, preparation, eating, and social relations
   as map branches when the completed food world already contains them.
6. Do not infer that the user is a farmer, fisher, chef, factory owner, or owner
   of any footage, cases, supply chain, health expertise, or regional authority.

The structured hypotheses live in `references/incubation-profile.json`. This
file is a shadow evaluation artifact and must not be copied into `skills/public/`
without a separately recorded promotion decision.
