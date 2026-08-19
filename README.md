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
- Symptoms map onto a **fixed ontology of 30 Japanese terms** (29 human-verified, 1 pending final sign-off).
- **The model never generates Japanese.** It *selects* from pre-verified terms. Every Japanese
  string that reaches a dispatcher was checked by a fluent human beforehand.

It's caller-side and pre-dispatch, which is a different problem from 救急ボイストラ — the
Fire Agency's own crew-side phrasebook, deployed to 96% of fire departments. That tool
translates what a panicking family says on scene; it structurally cannot know the patient's
address, age, or medical history in advance. This can.

## Who it's for

A household with a **known at-risk person** — an elderly relative with a heart condition — where
a family member with limited Japanese may be the one who finds them.

The app runs on a **home device, already open**, model already warm. In an emergency the caller
dials 119 on their **phone**, puts it on **speakerphone**, and works the app while holding the
phone toward its speaker. Two devices, deliberately: a phone can't inject app audio into a live
call — call and media audio are separate streams, and echo cancellation would suppress it anyway.

This does **not** help someone alone, away from home, or without the device set up. It's a home
emergency tool, which is narrower than "helps foreigners call 119" — and it's what every design
decision here actually fits.

## How it works

**Dial 119 first. Always** — never delay the call to prepare a better message.

```
  ☎️  119 dialled, phone on speakerphone
        ↓
  🚨 tap EMERGENCY  →  plays IMMEDIATELY, needs nothing computed:
        「救急です。場所は東京都江東区…」
        ↓  ~15 seconds in. Type + location. THE AMBULANCE IS DISPATCHED.
        ↓
        ↓   everything below happens while it is already en route
        ↓
  🎤 speech, in the caller's own language
        ↓  Whisper small, language taken from the profile (override available)
  📝 transcript in their language  →  shown for confirmation
     + English translation (Whisper's translate task) → fed to the classifier
        ↓  ← caller confirms: "is this what you said?"
  🧠 SLM classification against the 30-entry ontology
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

Emergency dispatch works on **location and call type, not diagnosis** — the ambulance rolls
immediately and the crew is updated by radio while driving. Travel time dwarfs everything else,
so gathering symptoms before dispatching would only add delay to every case. The remaining
details still arrive minutes before the crew does, and they do real work: upgrading the response
(PA連携 sends a fire engine alongside for a suspected arrest), pre-briefing the crew, and
attacking the on-scene delay the FDMA measured.

This is the NET119 pattern — the Fire Agency's own caller-side app for people with hearing and
speech disabilities also connects on type + location first and handles details afterwards.

It also means **inference latency is a polish problem, not a safety one.** Help is already moving
before the model has finished thinking.

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

**Classification** — 52-case labelled test set (`benchmark/eval_slm.py`), and the same cases
perturbed to simulate panicked speech (`benchmark/eval_disfluent.py`):

| | Clean | Panicked |
|---|---|---|
| Exact-match | 94% | — |
| Precision | 0.98 | 0.96 |
| Recall | 0.96 | 1.00 |
| F1 | 0.97 | 0.98 |
| Fabrications | 1 | 2 |

(Clean-speech numbers as of the 30-entry ontology, 2026-08-19 — splitting `fall` from
`collapsed` cost 2 points of exact-match and 1 fabrication, the honest price of asking the
model to resolve an ambiguity English itself doesn't disambiguate. All 3 remaining failures —
1 fabrication, 2 misses — are unrelated pre-existing cases, unchanged by the split.)

Disfluency does not degrade accuracy overall — exact-match and F1 are essentially unchanged. It
does shift the *kind* of error: under noise the model over-includes, so recall rises and
precision falls. Over-reporting is the safer direction, but fabrications are not zero even on
clean English speech, so the honest claim is "very low," not "none."

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
- **Anything outside the ontology's ~30 entries is not conveyed.** This is deliberate: the
  alternative is unverified machine-generated Japanese on a live emergency call.
- **Four terms are aspect-ambiguous** (vomiting, seizure, bleeding, choking) — a seizure that has
  stopped reads differently in Japanese from one still happening. The caller chooses on the
  confirmation screen rather than the model guessing, because a wrong guess could under-prepare
  the crew.
- **Whisper accuracy varies a lot by language**, and is weakest for some whose speakers are most
  vulnerable. No claim of uniform coverage. Two of the nine offered languages (Chinese, Korean)
  have been run end to end; the other seven have not.
- **Translation loses negation.** Non-English speech is translated to English before
  classification, and in testing "there is no response" came back as its opposite in both
  languages. Consciousness is unaffected — it comes from a forced button, never the model — but
  the risk is real for other symptoms, and the confirmation screen is the only backstop.
- **The interface is in English**, including both confirmation screens. A caller who reads
  neither Japanese nor English can still be guided by the flow, but cannot fully verify what the
  app understood — which weakens the safety loop for exactly the people who need it most.
- **Panicked, disfluent speech is untested.** Accent is tested; panic is not.
- **Outbound only.** After dispatching, Japanese dispatchers give 口頭指導 — talking the caller
  through CPR and positioning, in Japanese. That is genuinely life-saving and we don't handle it.
- One stored patient profile, English-first in practice, and no GPS.

On GPS specifically: it's absent by choice, not omission. A laptop has no GPS chip and locates by
WiFi/IP triangulation, which cannot produce a room number — while `profile.json` already holds
one, exactly. For a home emergency, a stored verified address beats an estimated position.

## Running it

Requires **Python 3.12** (OpenVINO has no wheels for 3.13+).

```bash
python3.12 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

First run opens straight to a **setup screen** — no profile exists yet. Enter your postal code
and it looks up your prefecture/city/ward in Japanese automatically (only place in the whole
project that touches the network, and only when you press that button — the emergency path
stays fully offline). Fill in the rest, save, and the app renders the Japanese audio for your
details right there before returning you to the emergency button.

(`tools/setup_profile.py` is the same thing as a terminal prompt, for a headless machine with
no browser.)

**The app never synthesises speech at runtime** — every sentence it can say is pre-rendered into
`data/audio/`, which is why it doesn't need a Japanese voice installed on the machine running it.
That works only because the ontology is a closed set. Rebuild with `python tools/build_audio.py`
after changing the ontology; it needs a machine with a Japanese voice, and the output is portable.

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
python benchmark/bench_whisper.py --audio data/bench_clip.wav
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
data/ontology.json          the ontology (verified Japanese terms) — the heart of the project
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
