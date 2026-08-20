---
name: incubate-gift-human-relations
description: >-
  Use when business sells gifts, souvenirs, or material-qualified gifts,
  including gold gifts. Expands gifting into human relations. Excludes jewelry
  or investment when gifting is not the business.
license: MIT
compatibility: DeerFlow v6 incubation profiles
metadata:
  author: DeerFlow v6 content-intelligence project
  version: "1.0.1"
  lifecycle: active
  source: docs/content-intelligence-v6/audits/A116-vertical-incubation-skills.md
---

# Gift And Human Relations Incubation

Use this Skill only to supply versioned domain hypotheses and a reviewable default content root to the generic incubation brain. It does not choose the final account route, write account positioning, or replace current evidence.

## Operating Contract

1. Keep the user's exact business expression unchanged.
2. Treat material, price, craft, region, and occasion as possible qualifiers, not automatic content roots.
3. Compare the gift object with the recurring actions of giving, receiving, returning, refusing, owing, thanking, and remembering.
4. Check whether those actions enter a larger concrete world of human relationships: affection, favor, face, obligation, status, boundaries, reciprocity, and power.
5. Keep any single occasion as a branch unless the user explicitly says that occasion is the business itself.
6. Do not infer that the user has cases, footage, customers, expertise, supply, or a particular sales channel.

For an account-starting or positioning request, call:

```text
develop_account_strategy(
  user_request=<the user's exact words>,
  incubation_skill="incubate-gift-human-relations"
)
```

Runtime resources:

- [Incubation profile](references/incubation-profile.json)
- [Evaluation manifest](evals/evals.json)
- [Acceptance receipt](evals/acceptance.json)
- [Acceptance evidence](evals/evidence/acceptance-evidence.json)

The tool loads the incubation profile itself. Do not copy it into the user request. The profile's default root is the current versioned map default for this vertical, not a user-confirmed account positioning decision.

Runtime exposure requires all four resources to match the complete activation package. The evaluation files govern activation; they are not extra instructions for the marketing decision.
