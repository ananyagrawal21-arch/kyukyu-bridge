# 救急ブリッジ / Kyūkyū-Bridge

**An offline, on-device co-pilot for the first 60 seconds of a Japanese 119 emergency call,
for callers who don't speak Japanese.**

Press one button, say what's happening in your own language, confirm what the app understood,
and it produces — and speaks aloud — a structured Japanese briefing a dispatcher can act on.
Everything runs locally. No network, no cloud, no call data leaving the device.

---

## The problem

Japan's Fire and Disaster Management Agency measures the cost of the language barrier directly:
foreign patients' **on-scene time runs 3–6 minutes longer than average**, explicitly because
communication takes time (Sapporo City Fire Bureau data). The agency links this to reduced
survival rates.

The agency is also blunt about why generic translation doesn't solve it:

> 既存の多言語自動翻訳システムを導入する消防機関も出てきているが、救急用のフレーズや傷病者との
> やり取りの面で使い勝手の良いものになっていない

— existing general-purpose translation systems aren't fit for emergency phrasing or patient
interaction.

The real bottleneck in those opening seconds isn't translation *quality*. It's that a panicking
person cannot produce structured, dispatcher-usable information at all — in any language.

## What this does differently

The system's advantage is **preparation**, not out-comprehending panicked speech:

- Address, age, sex, known conditions, and names are stored in advance and delivered instantly.
- Symptoms map onto a **fixed ontology of 29 human-verified Japanese terms**.
- **The model never generates Japanese.** It *selects* from pre-verified terms. Every Japanese
  string that reaches a dispatcher was checked by a fluent human beforehand.

It's caller-side and pre-dispatch, which is a different problem from 救急ボイストラ — the
Fire Agency's own crew-side phrasebook, deployed to 96% of fire departments. That tool
translates what a panicking family says on scene; it structurally cannot know the patient's
address, age, or medical history in advance. This can.

## How it works

```
  🎤 speech (any language)
        ↓  Whisper small, language forced from profile (override available)
  📝 English transcript
        ↓  ← caller confirms: "is this what you said?"
  🧠 SLM classification against the 29-entry ontology
     Stage A  candidate generation (high recall)
     Stage B  whole-list review pass (anti-fabrication)
        ↓  ← caller confirms: "is this what you meant?"  (can remove AND add)
  ❓ forced questions for the three vital signs dispatchers assess
     consciousness · breathing · circulation  — never guessed by the model
        ↓
  🇯🇵 Japanese briefing, composed from verified terms only
        ↓
  🔊 spoken aloud, one paced chunk at a time
```

### Safety architecture

Three rules the design refuses to break:

1. **No generated Japanese.** The model returns ontology *IDs*. Japanese is looked up, never
   written. Hallucinated Japanese cannot reach a live emergency call.
2. **Critical binary vitals bypass the model entirely.** Consciousness, breathing, and
   circulation come from forced-choice buttons — a small model was measured inverting them
   ("still awake" → unconscious), the most dangerous error possible here.
3. **Two human confirmation loops.** One on the transcript (did we *hear* you right?), one on
   the interpretation (did we *understand* you right?). Failures get caught, not delivered.

Supporting decisions: unknown values are omitted rather than guessed — an unconfirmed patient
identity drops age/sex/conditions entirely, and an unconfirmed location says 「今、自宅にいません。」
rather than asserting a possibly-wrong address. A wrong address is worse than no address.

## Measured results

**Classification** — 40-case labelled test set (`benchmark/eval_slm.py`):

| | |
|---|---|
| Exact-match | 90% |
| Precision | **1.00** — zero fabrications |
| Recall | 0.89 |
| F1 | 0.94 |

Precision matters most: the system never invented a symptom. All remaining errors are
under-reporting, which is the safe direction.

**Intel / OpenVINO** — Whisper `small`, 6.5s clip, Intel CPU:

| Runtime | Time | Speedup |
|---|---|---|
| PyTorch | 14.59s | 1.00× |
| OpenVINO FP | 10.56s | 1.38× |
| OpenVINO INT8 | 13.79s | 1.06× |

All three produced matching transcripts. INT8 barely beating FP is unexpected and not yet
explained — recorded honestly rather than omitted. SLM numbers on Intel hardware are pending.

**Speech-to-text robustness** was tested on real non-native English from the L2-ARCTIC corpus
(Vietnamese and Hindi speakers), not synthetic accents.

## Honest limitations

- **It only asks questions it anticipated.** Open-ended clarification is the dispatcher's job.
  The claim is "the opening 60 seconds", not "the conversation".
- **Anything outside the 29 ontology entries is not conveyed.** This is deliberate: the
  alternative is unverified machine-generated Japanese on a live emergency call.
- **Four terms assume ongoing aspect** (vomiting, seizure, bleeding, choking). If a seizure has
  already stopped, we still say けいれんしています. The default errs toward over-preparing the
  crew — see `OPEN_DECISIONS.md`.
- **Whisper accuracy varies a lot by language**, and is weakest for some whose speakers are most
  vulnerable. No claim of uniform coverage.
- **Panicked, disfluent speech is untested.** Accent is tested; panic is not.
- One stored patient profile, English-first in practice, and no GPS yet.

## Running it

Requires **Python 3.12** (OpenVINO has no wheels for 3.13+).

```bash
python3.12 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp data/profile.example.json data/profile.json           # then edit with real details
streamlit run app.py
```

Optional but strongly recommended — convert the SLM to OpenVINO INT8 once:

```bash
python benchmark/convert_slm.py
```

Without `models/`, the app falls back to plain PyTorch and prints a warning. The conversion is
memory-hungry — a 16 GB machine was measured being OOM-killed partway through loading the
checkpoint. The resulting `models/` folder is portable across machines and architectures, so
converting once on a larger machine and copying it across is a valid route.

**Reproducing the measurements:**

```bash
SLM_MODEL="Qwen/Qwen2.5-3B-Instruct" python benchmark/eval_slm.py
python benchmark/bench_whisper.py --audio data/test_recording1_converted.wav
```

## Layout

```
app.py                      Streamlit UI — the one-button flow, as a phase state machine
src/stt.py                  Whisper speech-to-text, language forced from the profile
src/slm_classify.py         two-stage classifier — selects ontology IDs, never writes Japanese
src/ontology.py             loads the ontology
src/briefing_template.py    composes Japanese from verified terms; owns the register rules
src/caller_profile.py       stored address / patient / caller details
src/pipeline.py             wiring, plus a CLI for testing without the UI
src/speak.py                offline Japanese TTS, pluggable backends
data/ontology.json          the 29 verified terms — the heart of the project
benchmark/                  evaluation and Intel/OpenVINO conversion scripts
OPEN_DECISIONS.md           full dated decision log, including reversals and rejected ideas
```

`OPEN_DECISIONS.md` is the real record of how this was built — what was tried, measured,
rejected, and why. Ideas that failed are kept there deliberately.

## Notes

Ontology terms were grounded in the FDMA's official 緊急度判定プロトコル Ver.1 and verified by a
fluent speaker. Accent testing used L2-ARCTIC (CC BY-NC 4.0, gated access), which is not
redistributed here. `data/profile.json` is gitignored — it holds a real home address and
medical details.

No license yet; all rights reserved for now.
