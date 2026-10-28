# Kyūkyū-Bridge — working agreement

## What this is

An assistant that lets a person in Japan who does not speak Japanese communicate with a 119
emergency dispatcher. Whisper (STT) → Qwen2.5-3B (Stage A: propose symptoms, recall) → fine-tuned
mDeBERTa NLI checker (precision), selecting from a closed, human-verified ontology. Built solo by a
high-school founder in Tokyo.

**Target architecture (decided 2026-10-12, see OPEN_DECISIONS.md):** the AI runs ON THE PHONE (audio
never leaves it, no cloud fallback); the server is a thin, reliable relay with no inference and no
persistent medical profiles; delivery is tiered (tier 0 = profile on dial, no AI). Today the laptop
stands in for the phone. OpenVINO is used for development/evaluation; phone runtimes are chosen after
a phone benchmark.

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
- **Existing solutions (NET119, 救急ボイストラ, 三者間同時通訳, Smart911) are references, not role
  models.** Do not assume their design decisions are correct for us. Smart911 is the closest
  reference — see `POSITIONING.md` §6 for the comparison table.
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

Full local working context (gitignored, loaded automatically if present): @PROJECT_CONTEXT.md

Then read `HANDOFF.md`, `ARCHITECTURE_EVALUATION.md` and the end of `EXPERIMENT_LOG.md`. In short: the
target architecture is decided (local-first AI on the phone, tiered delivery, thin relay); the fine-tuned NLI
checker replaces Stage B and runs in the app with Stage A on llama.cpp Q4_K_M; the technical-depth program
(L1–L5, M1–M7, "possible" tag, uncertainty routing) is decided in ARCHITECTURE_EVALUATION.md; next is plan
mode for the MVP build (phone app, relay + console, locked output). This GitHub repo is PUBLIC — never put
personal details or competition strategy in tracked files.

Information reaches the dispatcher as **data**, via FDMA's 標準インターフェイス, onto their console.
The voice call still happens in parallel so the dispatcher can hear the room and deliver 口頭指導.

## Corrections — do not repeat these mistakes

**Model size is not a barrier to phone deployment.** What ships TODAY is ~3.9 GB: Qwen2.5-3B
INT8 2.9 GB + Whisper small 926 MB, because the OpenVINO Whisper (242 MB) is OFF by default
(`KYUKYU_OV_STT` in `src/stt.py`). With it enabled it would be ~3.1 GB. Check which before
quoting either. Phones have 128 GB+ storage and 8–16 GB RAM; mobile games
ship larger. `OPEN_DECISIONS.md:790` already records INT4 3B at ~1.9 GB as "fine on any modern
phone", with 22–50 tok/s measured on phone silicon by others.

The real barrier to running this on a phone is that **OpenVINO is an Intel runtime and does not
run on phone chips.** Porting means a different runtime (llama.cpp / whisper.cpp / MLC), which
means re-benchmarking everything and losing the Intel claim on the caller's device. That is a
runtime-compatibility problem. Do not describe it as a size or footprint problem.

**The 4.6 GB figure in `models/` includes `qwen2.5-1.5b-ov-int8`**, which was tested and rejected
(it doubled fabrications). It does not ship. Never quote 4.6 GB.
