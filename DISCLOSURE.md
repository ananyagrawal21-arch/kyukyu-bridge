# GenAI Tool Usage Disclosure

*Kyūkyū-Bridge (救急ブリッジ) — Intel AI Global Impact Festival 2026*

This document exists because the evaluation rubric asks teams to list every generative-AI tool
used during development. It is a factual account of what was used and for what. It does not
assign itself a score — the division of work is described plainly so that a reader can judge it.

## Tools used

| Tool | Used for |
|---|---|
| **Claude (Anthropic)** | The substantial one. Implementation of application code, refactoring, code review, debugging, research synthesis from Japanese government sources, and drafting of documentation including parts of this repository's written material. |
| **ChatGPT (OpenAI)** | Occasional early-stage brainstorming and sanity-checking of ideas. |

No generative AI was used to produce any Japanese text that the application speaks to an
emergency dispatcher. See "The one hard line" below.

## What the founder did personally

- **Every architectural and product decision.** The scope (indoor, registered address), the
  decision to dial 119 first, the two-device acoustic path, the closed-ontology safety model,
  the choice to ask the human rather than let the model guess on clinically critical fields,
  and the restructure that dispatches the ambulance in ~15 seconds instead of ~60.
- **All Japanese-language verification.** Every one of the 31 ontology terms was checked by the
  founder, a fluent Japanese speaker resident in Japan, as *rendered output* rather than as raw
  strings. That review is what caught two real defects: a politeness-register error that produced
  「頭が痛いですと言っています」, and an over-claim in the wording for absent pulse.
- **The domain research.** Locating and reading the FDMA's 緊急度判定プロトコル Ver.1, the
  救急ボイストラ briefing documents, and the NET119 material; deciding what they implied.
- **The clinical distinctions.** The three-way split between 倒れました / 転倒しました /
  転落しました came from the founder correcting an assistant's incorrect claim that 倒れました
  implies a medical cause. It does not.
- **Direction and correction throughout.** The assistant was wrong on several occasions and was
  corrected — those corrections are recorded in `OPEN_DECISIONS.md`, which is kept as an honest
  engineering log rather than a highlight reel.

## What the AI assistant did

- Wrote a large share of the application code from the founder's specifications and decisions.
- Ran the benchmark harnesses and reported measured results.
- Found bugs during review, including several the founder then judged and prioritised.
- Drafted documentation from material and decisions the founder supplied.

**Stated plainly: this is not a project where AI was limited to brainstorming.** It was used for
implementation. The design, the domain knowledge, the Japanese, and every judgement call about
what was safe to ship are the founder's.

## The one hard line

**No generative model produces any Japanese that reaches a live emergency call.**

This is the central safety property of the whole system, and it is the reason the ontology is a
closed, human-verified set rather than a translation layer. Every Japanese sentence the app can
speak is either a fixed template or an ontology term that a human verified in advance, and every
one of them is pre-rendered to audio before the app ever runs. A language model selects *which*
pre-verified terms apply to what the caller said. It never writes Japanese.

The same rule governs the address: prefecture and city come from a postal-code lookup, the
district from Japan's national mapping authority (国土地理院), the building name from
OpenStreetMap. Where no authoritative lookup exists, the app asks the human or says nothing. It
never generates a place name.

## Reproducibility

`OPEN_DECISIONS.md` records the reasoning, the measured results, the rejected options and the
mistakes, with dates. It is the audit trail for everything claimed here.
