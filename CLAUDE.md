# Kyūkyū-Bridge — working agreement

## What this is

An offline, on-device assistant that lets a person in Japan who does not speak Japanese
communicate with a 119 emergency dispatcher. Whisper (STT) + Qwen2.5-3B (classification into a
closed clinical ontology) running locally via Intel OpenVINO. Built solo by a high-school founder
in Tokyo.

## Read these before proposing anything

- `POSITIONING.md` — the architecture decision, the regulatory pathway, why the design is what
  it is. **Read this first.** It explains the pivot away from speaking into the call.
- `OPEN_DECISIONS.md` — the full decision log. Long. Search it before re-litigating anything;
  most "new" ideas were already tried and rejected with reasons.
- `README.md` — the public write-up, including measured benchmarks.
- `RESPONSIBLE_AI.md` — safety claims. Anything asserted here must be true in code.

## How to work with me (the founder)

- **Give me git commands to run. Do not run them yourself.** I am learning git and I need to type
  them.
- **Do not change UI text unless I explicitly say "make UI changes."** This includes button
  labels, captions and on-screen wording.
- **Explain simply.** Plain language, short sentences, concrete examples. Not jargon, not dense
  compressed prose. If I say I do not understand, re-explain from the start rather than adding
  detail to the same explanation.
- **Do not spawn subagents or run councils unless I ask for one.**
- **Existing solutions (NET119, 救急ボイストラ, 三者間同時通訳) are references, not role models.**
  Do not assume their design decisions are correct for us.
- When I push back on a claim, check it against the repo or a primary source before defending it.
  I have been right more than once and I would rather be corrected than agreed with.

## Non-negotiable

- **`data/profile.json` and `data/audio/profile/` contain a real home address. Never commit
  them, never print the address in chat output.** Both are gitignored — keep it that way.
- **Accuracy over impressiveness.** No overclaiming, no rounding in our favour. Every number in
  the docs must survive a judge checking it. If a measurement contradicts a claim, the claim
  changes.
- **The model never generates Japanese that reaches a dispatcher.** Output is drawn from the
  closed, human-verified ontology in `data/ontology.json`. This is the core safety property.
- **English on screen, Japanese in the data.** The user never has to read or produce Japanese.
- **The UI guides, it never presents.** Every screen should tell the user what to do next.

## Repos

- `kyukyu-bridge` (this one, private) — full comments, the decision logs, the benchmark work.
- `kyukyu-public` — the published copy, comments trimmed. **I edit the public one; you keep
  private in sync.** Code must stay behaviour-identical between them.

## Evaluation — do not skip

- `benchmark/slm_testset.json` — 52 cases. **Frozen.** Its figures are published in the README.
  Never edit these cases; add new ones elsewhere.
- `benchmark/diagnostic_probe.json` — 43 cases in six groups (recognition, abstention, negation,
  temporal, out-of-coverage, panic). Characterisation, not a tuning set.
- `benchmark/harness.py` — scores precision/recall/F1 for Stage A and Stage A+B separately, plus
  a cardiac-arrest false-positive count. **Any CPA false positive fails the run regardless of F1.**
- One change per run. Never stack changes and then ask which one worked.

## Running it

```bash
.venv/bin/streamlit run app.py     # NOT bare `streamlit` — that picks Python 3.14, which has
                                   # no transformers and no openvino
```

## Where the project is now

The two-device problem is resolved: the app no longer speaks into the call. Information reaches
the dispatcher as **data**, via FDMA's 標準インターフェイス, onto their console. The voice call
still happens in parallel so the dispatcher can hear the room and deliver 口頭指導.

Next: build the two-way demo — caller's phone ↔ server ↔ dispatcher console. See the end of
`POSITIONING.md`.
