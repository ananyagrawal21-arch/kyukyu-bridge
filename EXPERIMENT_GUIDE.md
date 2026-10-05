# Experiment guide — can a small "meaning checker" replace Stage B?

Written 2026-10-05 for the founder to run hands-on in Cursor. Read top to bottom once before
starting. Every command is run from inside `/Users/User/Desktop/kyukyu-bridge`.

---

## 0. What "an experiment" means here — and how it differs from KaiGo-AI

KaiGo-AI (last year's winner, `github.com/Atharvkk/KaiGo-AI`) tested with **standalone files**:
`Whisper_Standalone.py`, `GPT_NEO_Standalone.py`. Each loads one model, feeds it **one** input,
prints the output and the time. `Benchmarks.txt` records only **speed**.

That answers *"does it run, and how fast?"* It cannot answer *"is it better?"* — one input,
judged by eye, proves nothing about accuracy.

We do both:
1. **A standalone file first** (KaiGo-style) — a quick sanity check that the model loads and
   gives sensible answers on 3–4 sentences.
2. **Then a real evaluation** — the same model on **many labelled cases**, scored with numbers,
   compared against the current system on exactly the same cases.

Only step 2 can decide anything.

---

## 1. The question this experiment answers

The app understands a caller in two steps:

```
Stage A  "the guesser"  reads the sentence, proposes possible symptoms   (Qwen)
Stage B  "the checker"  removes the wrong proposals                      (Qwen again)
```

We proved (BUILD_PLAN.md, B1) that **Stage B compares proposals against each other** instead of
against the sentence, so it throws away correct ones. Example:

```
"he collapsed and now he's convulsing on the floor"
Stage A: collapsed, seizure     ← both correct
Stage B: collapsed              ← deleted seizure
```

**The question:** if we replace Stage B with a small model built only to answer *"does sentence 1
mean sentence 2?"*, do we keep the correct symptoms **and** still remove the wrong ones **and**
never raise a false cardiac-arrest alarm?

---

## 2. Words you need

| Word | Meaning | Example from our data |
|---|---|---|
| **Test case** | one sentence + the correct answer | "she feels boiling hot to the touch" → `high_fever` |
| **Label** (expected) | the correct answer, written by a human | `{high_fever}` |
| **Prediction** | what the system answered | `{}` (it missed) |
| **Miss** | a correct symptom the system left out | `high_fever` above |
| **Wrong extra** (false positive) | a symptom the system added that wasn't there | `chest_pain` for "it hurts, it really hurts" |
| **Precision** | of everything the system said, how much was right | 0.961 = 96.1% of its answers were correct |
| **Recall** | of everything it should have said, how much it found | 0.925 = it found 92.5% |
| **F1** | one number combining both | 0.942 |
| **CPA false alarm** | a wrong `no_pulse`, `not_breathing`, `choking` or `body_cold` | starts CPR instructions for nobody. **Any one fails the run.** |
| **NLI** (natural language inference) | a model that reads two sentences and says: *implies* / *contradicts* / *neither* | "he's convulsing" → "The person is having a seizure." = implies |
| **Hypothesis** | the fixed sentence we write for each symptom | `seizure` → "The person is having a seizure." |
| **Score** | how strongly the model thinks "implies", from 0 to 1 | 0.93 |
| **Threshold** (cut-off) | the score above which we keep a symptom | keep if score ≥ 0.50 |
| **Baseline** | the current system's numbers — what we have to beat | section 4 |
| **Dev set** | NEW cases used to choose the threshold | written for this experiment |
| **Test set** | cases used only to report the final result, never to tune | the 52 and the probe |

**Why the dev set must be separate:** if you choose the threshold by looking at the 52, you will
pick whatever happens to fit those 52 sentences — and the result will look better than it really
is. It's like seeing the exam before writing the answer key. So: **choose on the dev set, report
on the 52 and the probe, once.**

---

## 3. What already exists in the repo

| File | What it is | Run it |
|---|---|---|
| `benchmark/slm_testset.json` | **52 test cases. FROZEN — never edit.** | — |
| `benchmark/diagnostic_probe.json` | 43 harder cases in 6 groups (recognition, abstention, negation, time, out-of-coverage, panic). **Never tune on these.** | — |
| `benchmark/harness.py` | scores any variant: precision, recall, F1, exact matches, CPA false alarms, for Stage A alone and A+B | `.venv/bin/python benchmark/harness.py` |
| `benchmark/.stage_a_cache.json` | **saved** Stage A proposals for every case (Sep 13, OpenVINO INT8) | read by the scripts |
| `benchmark/.stage_b_cache.json` | **saved** Stage B decisions | read by the scripts |
| `benchmark/error_analysis.py` | lists every miss and wrong extra, and **which stage** caused it | `.venv/bin/python benchmark/error_analysis.py` |
| `benchmark/b_isolation.py` | the experiment that proved Stage B's root cause | needs the model, ~15 min |

**The caches are why this experiment is fast.** Stage A's proposals are already saved, so the NLI
model only has to judge them. No Qwen needed.

---

## 4. The baseline — the numbers to beat

Current system, OpenVINO INT8, from the cache:

| | Precision | Recall | F1 | Exact | CPA false alarms |
|---|---|---|---|---|---|
| 52 — Stage A only | 0.855 | **1.000** | 0.922 | 43/52 | 0 |
| **52 — A + B (what ships)** | **0.961** | **0.925** | **0.942** | **46/52** | **0** |
| probe — Stage A only | 0.543 | 0.926 | 0.685 | 24/43 | **5** |
| **probe — A + B (what ships)** | **0.800** | **0.889** | **0.842** | **37/43** | **0** |

Read it like this:
- **Stage A finds every correct symptom on the 52 (recall 1.000).** All the misses come from Stage B.
- **Stage A alone raises 5 false cardiac-arrest alarms on the probe.** Stage B removes all 5. A new
  checker must also remove all 5 — this is the hardest bar.

**Success** = recall goes up from 0.925, precision stays near 0.961, and CPA false alarms stay at 0
on both sets.

---

## 5. The experiment, step by step

### Step 0 — install one missing library

The NLI model's tokenizer needs `sentencepiece`, which is not installed.

```bash
.venv/bin/pip install sentencepiece
```

### Step 1 — download the model and convert it to OpenVINO

Model: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` — 279M parameters, 100 languages,
trained on 2.7M sentence pairs. `optimum-cli` (already installed) downloads it from Hugging Face and
converts it to OpenVINO in one command:

```bash
.venv/bin/optimum-cli export openvino --model MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 --task text-classification --weight-format int8 models/nli-mdeberta-ov-int8
```

- `--task text-classification` — this model classifies a sentence PAIR into 3 labels
- `--weight-format int8` — compress to INT8, like Qwen
- `models/nli-mdeberta-ov-int8` — where it goes. `models/` is gitignored, so it is never committed.

If INT8 fails for this model, run the same command without `--weight-format int8` (full precision)
and note it — that is a result too.

### Step 2 — the standalone sanity check (KaiGo-style)

**Create `benchmark/nli_sanity.py`.** Goal: prove the model loads and its answers make sense, on
a handful of pairs. Starting point:

```python
import sys
import time
from pathlib import Path

import torch
from optimum.intel import OVModelForSequenceClassification
from transformers import AutoTokenizer

PATH = Path(__file__).resolve().parent.parent / "models" / "nli-mdeberta-ov-int8"

tok = AutoTokenizer.from_pretrained(PATH)
model = OVModelForSequenceClassification.from_pretrained(PATH)
print(model.config.id2label)   # CHECK THIS - which number means "entailment"?

pairs = [
    ("he collapsed and now he's convulsing on the floor", "The person is having a seizure."),
    ("she feels boiling hot to the touch", "The person has a high fever."),
    ("he had a seizure last month but nothing today", "The person is having a seizure."),
    ("he did not hit his head", "The person has a head injury."),
]
for premise, hypothesis in pairs:
    start = time.time()
    inputs = tok(premise, hypothesis, return_tensors="pt")
    probs = torch.softmax(model(**inputs).logits, dim=-1)[0]
    scores = {model.config.id2label[i]: round(float(p), 3) for i, p in enumerate(probs)}
    print(f"{time.time() - start:.3f}s  {scores}\n   {premise!r} -> {hypothesis!r}")
```

Run:

```bash
.venv/bin/python benchmark/nli_sanity.py
```

**What to look for:** pair 1 and 2 should lean *entailment*. Pairs 3 and 4 should NOT — ideally
*contradiction*. Also note the time per pair. **Write down what you see before moving on.**

### Step 3 — write the 31 hypotheses

**Create `data/nli_hypotheses.json`** — one plain sentence per symptom id in the ontology
(`consciousness_states`, `symptoms`, `events` in `data/ontology.json`):

```json
{
  "seizure": "The person is having a seizure.",
  "high_fever": "The person has a high fever.",
  "head_injury": "The person has a head injury."
}
```

Rules:
- One simple sentence, present tense, "The person …".
- Describe the symptom, not the cause. No clinical jargon a caller would not use.
- **You write or review every one.** These are the new "fixed text" of the system, like the
  ontology itself. Write them BEFORE you look at any scores, so you are not tempted to tune them.

### Step 4 — write the dev set

**Create `benchmark/dev_set.json`** — about 40 NEW cases, never seen by the system, in the same
format as the 52:

```json
{"cases": [
  {"transcript": "my dad is shaking all over and won't stop", "expected": ["seizure"]},
  {"transcript": "she's burning up, I can feel the heat from her forehead", "expected": ["high_fever"]}
]}
```

Include a mix, roughly in this proportion:
- **plain** descriptions (10)
- **figurative / everyday wording** (8) — "boiling hot", "his back has gone"
- **negation** (6) — "he didn't hit his head"
- **time** (5) — "it stopped", "last week"
- **two or more symptoms** in one sentence (6)
- **cardiac-arrest traps** (5) — sentences that sound alarming but are NOT no-pulse / not-breathing

Do not copy or rephrase cases from the 52 or the probe. Then Stage A must propose candidates for
these new cases — that needs Qwen once. The harness's `stage_a()` does it and saves to the cache.

### Step 5 — score every Stage A proposal

**Create `benchmark/nli_score.py`.** For every case in the dev set, the 52 and the probe:
take Stage A's saved proposals, and for each proposal compute the NLI *entailment* score of
(caller's sentence → that symptom's hypothesis). Save everything to `benchmark/.nli_cache.json`,
so scoring only ever runs once.

### Step 6 — choose the threshold on the dev set, then report

1. On the **dev set only**, try thresholds from 0.05 to 0.95. For each, count: correct kept,
   wrong removed, CPA false alarms.
2. Pick the threshold with **zero CPA false alarms** and the **highest recall**.
   (Optional, as a separate run: a stricter threshold just for the four CPA ids.)
3. Apply that one threshold to the **52 and the probe, once**. Score with `harness.score()`, so the
   numbers are directly comparable with section 4.
4. Also time it: seconds per pair on this Mac. (The Intel laptop number comes later.)

### Step 7 — decide, and write it down

| Result | What it means | Next |
|---|---|---|
| Recall up, precision about the same, CPA 0 on both sets | **It works** | Replace Stage B in the app — as its own separate change |
| Recall up, precision clearly down | It is too lenient | Try it together with the negation gate — as a separate run |
| Fails figurative cases ("boiling hot") | Zero-shot is not enough | Next experiment: fine-tune this same small model |
| Any CPA false alarm it can't avoid | Not safe as the only checker | Record it; keep Stage B or combine |
| Worse overall | Negative result | Record it in OPEN_DECISIONS.md — it still counts |

Write the result, numbers and backend into `OPEN_DECISIONS.md` (4e) and tick B1's next step in
`BUILD_PLAN.md`. A failed experiment written down honestly is worth more than an unrecorded success.

---

## 6. The rules — these never bend

From `CLAUDE.md`:
- **`benchmark/slm_testset.json` is frozen.** Never edit, never tune on it.
- **The probe is for characterising, not tuning.**
- **One change per run.** Never change the hypotheses AND the threshold and then ask which helped.
- **Record the backend** (OpenVINO INT8, Mac) next to every number.
- **Any CPA false alarm fails the run, whatever F1 says.**
- **The model never writes Japanese.** The NLI model only scores English sentences we wrote. The
  Japanese still comes only from `data/ontology.json` — this experiment does not touch that.

---

## 7. Working in Cursor

1. **Open the folder:** File → Open Folder → `/Users/User/Desktop/kyukyu-bridge`.
2. **Pick the Python interpreter:** Cmd+Shift+P → "Python: Select Interpreter" →
   `.venv/bin/python` (Python 3.9.6). Not the system Python — that one has no OpenVINO.
3. **Run things in Cursor's terminal** (Ctrl+`), always with `.venv/bin/python …`.
4. **Before asking Cursor's AI anything, tell it:** *"Read CLAUDE.md and EXPERIMENT_GUIDE.md first.
   Never edit benchmark/slm_testset.json or benchmark/diagnostic_probe.json."* Cursor's AI does not
   know the project rules unless it reads them, and these two files are the ones it could damage.
5. **Commit with your own commands**, as always.

**Order of files you will create:**
`benchmark/nli_sanity.py` → `data/nli_hypotheses.json` → `benchmark/dev_set.json` →
`benchmark/nli_score.py`

**Expected time:** steps 0–2 well under an hour. Steps 3–4 (writing hypotheses and the dev set)
are the slow, important part — they are the human judgment the whole result rests on.
