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
  version: "1.2.0"
  lifecycle: active
  source: docs/content-intelligence-v6/audits/A116-vertical-incubation-skills.md
---

# Gift And Human Relations Incubation

Use this Skill only to supply versioned domain hypotheses and reviewable content-root candidates to the generic incubation brain. It does not choose the root or final account route, write account positioning, replace current evidence, or inject denied facts into the project Brief.

## Operating Contract

1. Keep the user's exact business expression unchanged.
2. Treat material, price, craft, region, and occasion as possible qualifiers, not automatic content roots.
3. Compare the gift object with the recurring actions of giving, receiving, returning, refusing, owing, thanking, and remembering.
4. Check whether those actions enter a larger concrete world of human relationships: affection, favor, face, obligation, status, boundaries, reciprocity, and power.
5. If the user explicitly names a single occasion, compare it with the larger recurring relationship world. Do not introduce a specific occasion the user did not state merely to complete a route or example list. Preserve an explicitly stated occasion; this is a source boundary, not a keyword ban.
6. When two roots overlap, prefer the plain-language world that can hold more concrete people, events, choices, and relationship changes. Extra theoretical layers in an etiquette or ritual frame are not, by themselves, evidence of a better account world.
7. Do not infer that the user has cases, footage, customers, expertise, supply, or a particular sales channel.

## Long-Term Account Check

- Compare three different editorial distances: the gift commodity, the act of giving, and how people maintain relationships. Do not blend them into one long label.
- A relationship-world route has not passed if every content example still centers the gift commodity or the act of gifting. It should also hold product-independent people, events, choices, misunderstandings, reciprocity, boundaries, status changes, and relationships where no object is exchanged. The business remains a possible return point rather than the surface subject of every item.
- For a long-term account-direction request, use at most one optional `explore_content_world` call with `answer_goal=content_opportunities` when the tool is available, but only after the commercial object and materially different audiences are understood. Use the map to test product-independent relationship branches, not to restart semantic intake or replace the Lead's judgment.
- For a bare business statement, keep examples at the relationship-pattern level and omit named occasions from the final answer, including parenthetical examples. If the user supplies an occasion, preserve it and judge it normally.
- Treat any proposed expert persona as conditional on user evidence. Never turn "见过很多案例", "懂人情", or similar authority into a fact or a requirement the user must pretend to satisfy. An assertion followed by uncertainty is still an unsupported assertion; write the condition as "if the user has..." from the start.

For an account-starting or positioning request, apply these principles as
domain attention, then return the judgment to the Lead. The Lead decides
whether any content-intelligence tool is useful; loading this Skill does not
require a tool call, lexical decomposition, content map, benchmark search, or
questionnaire. If one optional content map is used, treat it as working
material and do not recompute it with different wording.

Package resources:

- [Incubation profile](references/incubation-profile.json)
- [Evaluation manifest](evals/evals.json)
- [Acceptance receipt](evals/acceptance.json)
- [Acceptance evidence](evals/evidence/acceptance-evidence.json)

Do not read the runtime resources during an ordinary Lead conversation. The operating contract
above is the complete model-visible method. The profile and evaluation files are retained for
package verification, historical compatibility, and offline review; loading them adds stale route
hints without improving the current judgment.

Legacy typed tools may load the incubation profile themselves. Do not copy it into the user
request. Its preferred root is a rejectable candidate, not a default answer or a user-confirmed
account positioning decision. Supporting branch hints must never become forbidden words or
deterministic text classifiers.

Runtime exposure requires all four resources to match the complete activation package. The evaluation files govern activation; they are not extra instructions for the marketing decision.
