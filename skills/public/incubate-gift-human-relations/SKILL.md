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
  version: "1.3.4"
  lifecycle: active
  source: docs/content-intelligence-v6/audits/A116-vertical-incubation-skills.md
---

# Gift And Human Relations Incubation

Use this Skill only to supply versioned domain hypotheses and reviewable content-root candidates to the generic incubation brain. It does not choose the root or final account route, write account positioning, replace current evidence, or inject denied facts into the project Brief.

## Decisive Output Check

For a bare account-starting request, apply this check before returning the answer:

- Do not introduce marriage, childbirth, festivals, business banquets, or any other named occasion as the user's fact or as the default example. A named occasion is available only when the user supplied it, current evidence supports it, or it is explicitly labeled as a hypothetical illustration.
- If the Lead selects the human-relations world, include at least one concrete premise whose surface subject and audience-interest engine are a relationship event rather than the user's merchandise or a buying decision. Money, meals, favors, gifts, or other ordinary social objects may appear when they genuinely carry the relationship event; do not ban them by keyword.
- The qualifying premise must be about a person's choice and a relationship change, such as a favor, refusal, silence, boundary, misunderstanding, reciprocity, or status shift. It must remain understandable and worth watching when the user's gold product is removed or replaced; a product-selection question with relationship vocabulary does not qualify.
- Keep the commercial return at the account level. Do not force the product back into the qualifying premise merely to prove monetization.
- Do not give every topic a "gold's role", "product return", or sales-explanation paragraph. At least one far-field premise must finish its title, setup, and point of view without mentioning gold, a gift choice, or how the merchandise returns. Explain the account-level business connection once after the topic set instead.
- Label an invented scene as hypothetical at its first appearance. Do not add invented budgets, quantities, durations, customer requests, results, or authority to make it feel concrete.
- Never write "we made this for a company", "a customer told me", or another first-person customer case unless the user or observed evidence supplied that case. Rewrite an unevidenced example as an explicitly hypothetical scene.

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
- A relationship-world route has not passed if every content example still centers the gift commodity, a buying decision, or the act of gifting. It should also hold product-independent people, events, choices, misunderstandings, reciprocity, boundaries, and status changes. Ordinary money, meals, favors, or objects may appear as story elements when the relationship event remains the surface subject. The business remains a possible return point rather than the surface subject of every item.
- For a bare business statement, do not assume a named occasion is a user fact. A product-independent premise may use a user-provided event, a verified public event, or an explicitly labeled fictional or hypothetical scene. A named public event needs evidence before it is presented as fact. If the user supplies an occasion, preserve it and judge it normally.
- Never disguise a fictional or hypothetical scene as a customer story, testimonial, observed case, or research finding.
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
