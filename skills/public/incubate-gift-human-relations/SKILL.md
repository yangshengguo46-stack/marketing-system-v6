---
name: incubate-gift-human-relations
description: >-
  Use for account incubation when the user's actual business object is gifts,
  presents, gifting, corporate gifts, souvenirs, or a material-qualified gift
  such as gold gifts. Helps compare gift objects with the broader recurring
  world of giving, receiving, reciprocity, relationships, face, obligation,
  boundaries, and human relations. Do not use for jewelry, gold investment, or
  a wedding business unless gifting is itself the stated business object.
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

The tool loads `references/incubation-profile.json` itself. Do not copy that file into the user request. Its `default_root` is the current versioned map default for this vertical, not a user-confirmed account positioning decision.
