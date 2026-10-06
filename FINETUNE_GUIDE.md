# Fine-tuning guide — teaching the checker our task (experiment NLI-8)

Written 2026-10-06 for the founder to carry out in Cursor. Read it top to bottom once before
starting. Every command runs from `/Users/User/Desktop/kyukyu-bridge`, with `.venv/bin/python`.

Record every step in `EXPERIMENT_LOG.md` as you go — what you ran, the numbers, what broke and how
you fixed it. Failures included.

---

## 0. What we are doing, in plain words

**The objective (unchanged):** find the best Stage B — the step that decides which of Stage A's
guessed symptoms to keep.

**What we tried so far** (all in `EXPERIMENT_LOG.md`):
1. Why Stage B fails → it compares guesses against each other. *Proven.*
2. A ready-made "meaning checker" (NLI) instead of Stage B → kept more correct symptoms, but let
   in 3 false choking alarms. *Failed.*
3. Stage B + the checker rescuing what B threw away → a draw. *Not adopted.*

**Why the checker failed:** it is a general-purpose model. It was never taught emergency language,
so it is wrong in three specific ways:

| Weakness | Example from our runs |
|---|---|
| **Choking** — real and false look the same to it | real "it's stuck, he can't cough it out" scored 0.12; false "lips turning blue" scored 0.78 |
| **Lookalikes** | "pounding headache" → racing heart, 0.93 |
| **Time words** | "headache yesterday, fine now" → headache, 0.97 |

No line and no combination can fix a model that scores these wrongly. **So we teach it**: show it
several hundred examples of exactly these situations with the right answers, and let it adjust.
That is **fine-tuning**. Same model, same size, still converted to OpenVINO — it just learns our task.

**Then we measure it exactly like before**, on a test set it has never seen (`test2`, locked).

---

## 1. Rules — paste this into Cursor's AI before anything else

> Read CLAUDE.md, EXPERIMENT_GUIDE.md and FINETUNE_GUIDE.md first. Never edit
> benchmark/slm_testset.json, benchmark/diagnostic_probe.json or benchmark/test2_set.json.
> Training sentences must never copy or reword a sentence from those files or from
> benchmark/dev_set.json. Every training sentence must be something a real caller would plausibly
> say at the start of a 119 call. Use .venv/bin/python, never the system Python.

**The rules behind it:**
- **test2 is locked.** Its fingerprint is in the log. It is used once, at the end, to report.
- **Choose settings on the dev set, never on test2, the 52 or the probe.**
- **Realism:** no "he's fine now" sentences. Tricky cases sit inside real emergencies.
- **Target failure TYPES, never copy failure SENTENCES.** Writing more choking examples is right;
  rewording "lips turning blue" from the probe is cheating.
- **One change per run.** Training data, then training, then measuring — never change two things
  and ask which one helped.

---

## 2. Files involved

| File | Status | Role |
|---|---|---|
| `data/nli_hypotheses.json` | exists, **frozen** | the 28 symptom sentences — used for training AND testing, unchanged |
| `benchmark/dev_set.json` | exists, **v2** | choosing the line X |
| `benchmark/test2_set.json` | exists, **locked** | the final, clean result |
| `benchmark/dev_stage_a.py`, `dev_stage_b.py` | exist | step A — you add a `--set` option |
| `data/nli_train_sentences.json` | **you create** | step B — the training examples |
| `benchmark/check_overlap.py` | **you create** | step B — proves no training sentence copies a test sentence |
| `benchmark/nli_finetune.py` | **you create** | step C — the training |
| `benchmark/nli_score.py`, `nli_threshold.py` | exist | step E — you add options |

---

## Step A — saved results for the new test sentences

The checker only judges Stage A's guesses, and Stage B is the thing we compare against. Both must
exist for **test2 (34 new sentences)** and the **5 new dev v2 sentences**.

**Change** `dev_stage_a.py` and `dev_stage_b.py` so they take a `--set` option — `dev` (default) or
`test2` — and read `benchmark/dev_set.json` or `benchmark/test2_set.json` accordingly. Use Python's
`argparse` module. Nothing else in them changes.

**Run (Qwen — slow, 10–25 min for test2):**
```bash
.venv/bin/python benchmark/dev_stage_a.py               # dev: only the 5 new cases run
.venv/bin/python benchmark/dev_stage_b.py
.venv/bin/python benchmark/dev_stage_a.py --set test2   # all 34
.venv/bin/python benchmark/dev_stage_b.py --set test2
```
**Write in the log:** Stage A's recall on test2 (the "never proposed" count it prints) — that is the
ceiling no checker can beat on test2.

---

## Step B — the training examples

### B1. The file: `data/nli_train_sentences.json`

```json
{"sentences": [
  {"group": "choking", "transcript": "my daughter had a grape in her mouth and now she can't breathe or talk",
   "expected": ["choking"], "denied": []},
  {"group": "time", "transcript": "he had a seizure last year, today he's got a terrible headache",
   "expected": ["headache"], "denied": ["seizure"]}
]}
```

- `expected` — symptoms the caller describes now. Same label rules as the test sets (a symptom that
  STOPPED during this emergency still counts if it has a "has stopped" form).
- `denied` — symptoms the sentence explicitly rules out or puts in the past ("not", "last year",
  "it went away"). These teach the model **contradiction**.

### B2. How many, and what kind

**About 300 sentences.** Roughly 10 per symptom, weighted towards the weaknesses:

| Group | How many | What it teaches |
|---|---|---|
| plain + everyday wording | ~120 | the basics, many ways of saying each symptom |
| choking — real | ~25 | food, toys, coins, "can't talk", "grabbing throat", "went down the wrong way" |
| choking — lookalikes | ~20 | coughing from illness, asthma wheeze, vomiting, swelling throat |
| lookalikes | ~50 | pounding/throbbing head vs racing heart; numb vs weak; cold hands vs cold body; hot sweat vs cold sweat; shivering vs seizure; "seized up" back vs seizure |
| time | ~40 | yesterday / last week / years ago / "it went away" vs now; stopped-during-this-call |
| negation | ~30 | "not", "no", "didn't", "isn't" |
| multi-symptom | ~20 | 2–3 symptoms at once |

**Who writes them:** draft them with Cursor's AI, then **you review**. At minimum read every choking,
no_pulse and body_cold label, and one in five of the rest. Write down in the log how many you
checked and how many you corrected.

### B3. The overlap check: `benchmark/check_overlap.py`

Have it load every training sentence, and the sentences from the 52, the probe, dev and test2, and
report:
- **exact copies**
- **near-copies** — more than 50% of words shared (the same check used when test2 was written)
- **bad labels** — any id not in `nli_hypotheses.json`, or any of conscious / unconscious /
  not_breathing

**It must print "none" for all three before you train.** Reword anything it flags.

```bash
.venv/bin/python benchmark/check_overlap.py
```

---

## Step C — training: `benchmark/nli_finetune.py`

### C1. What the script must do

1. **Turn sentences into pairs.** Each pair is (caller's sentence, one symptom's hypothesis sentence)
   plus the right answer:
   - every symptom in `expected` → **entailment**
   - every symptom in `denied` → **contradiction**
   - up to 3 other symptoms → **neutral**: first the lookalikes of the expected ones (the list
     below), then random others. Never a symptom from `expected` or `denied`.
   About 300 sentences gives roughly 1,000–1,500 pairs.
2. **Hold back 10% of the SENTENCES** (not pairs) as a check set the model never trains on. This
   catches overfitting. Split by sentence, so the same sentence never sits on both sides.
3. **Load the base model** in PyTorch: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`
   (already downloaded during the OpenVINO conversion). Label numbers come from
   `model.config.label2id` — 0 entailment, 1 neutral, 2 contradiction. Check, don't assume.
4. **Train with a plain PyTorch loop** (no `Trainer` — `accelerate` isn't installed):
   tokenize pairs (max_length 128, padding, truncation) → batches of 8 → forward pass → loss →
   backward → optimizer step.
5. **Settings** (standard for this kind of model; write them in the log):

| Setting | Value | Why |
|---|---|---|
| learning rate | 2e-5 | small, so it adjusts without forgetting what it already knows |
| epochs | 3 | passes over the data. More risks memorising the examples |
| batch size | 8 | fits in 16 GB |
| optimizer | AdamW, weight decay 0.01 | the standard for this model family |
| seed | 42 (`random`, `torch`) | so the run can be repeated exactly |
| device | `mps` (Apple GPU), else `cpu` | |

6. **After each epoch, print:** training loss, and on the held-back 10%: loss and accuracy.
7. **Save** with `save_pretrained` — model AND tokenizer — to `models/nli-mdeberta-ft`
   (`models/` is gitignored).

### C2. Lookalike list (for the neutral pairs)

```
headache ↔ palpitations            numbness ↔ one_sided_weakness
cold_sweat ↔ body_cold ↔ pale_complexion
choking ↔ nausea, vomiting, difficulty_breathing
seizure ↔ back_pain, high_fever      collapsed ↔ fall ↔ fall_down
chest_pain ↔ severe_abdominal_pain   back_pain ↔ lower_back_pain
dizziness ↔ nausea                   drowning ↔ body_cold
```

### C3. Run, and what to expect

```bash
.venv/bin/python benchmark/nli_finetune.py
```
- Roughly 10–40 minutes on this Mac.
- **Training loss should go down each epoch.**
- **Held-back accuracy should go up, then level off.** If training loss keeps falling while
  held-back loss rises, the model is **memorising** — use fewer epochs. Log it either way.
- If `mps` errors: run with `PYTORCH_ENABLE_MPS_FALLBACK=1` in front of the command, or switch to `cpu`.

---

## Step D — convert to OpenVINO INT8

The same command as the first conversion, pointed at the trained model:

```bash
.venv/bin/optimum-cli export openvino --model models/nli-mdeberta-ft --task text-classification --weight-format int8 models/nli-mdeberta-ft-ov-int8
```
The same loading fix applies (fixed input size 1 × 128) — it's the same model design.

---

## Step E — score and compare

### E1. Changes to the scripts
- `nli_score.py`: add `--model-dir` (default `models/nli-mdeberta-ov-int8`) and `--cache`
  (default `benchmark/.nli_cache.json`), and include **test2** sentences in `all_sentences()`.
- `nli_threshold.py`: add `--cache`, and add **test2** to Part 2 and Part 3. Change the X rule to
  **zero CPA false alarms → best F1** (the method fix from NLI-7, instead of best recall).

### E2. Runs
```bash
# the ORIGINAL checker on the new sentences, for a fair three-way comparison
.venv/bin/python benchmark/nli_score.py
.venv/bin/python benchmark/nli_threshold.py

# the FINE-TUNED checker
.venv/bin/python benchmark/nli_score.py --model-dir models/nli-mdeberta-ft-ov-int8 --cache benchmark/.nli_ft_cache.json
.venv/bin/python benchmark/nli_threshold.py --cache benchmark/.nli_ft_cache.json
```

---

## Step F — decide, and write it down

**Success (decided in advance, in the log):** on **test2** and on the 52, the fine-tuned checker
beats Stage B on F1, with **zero** cardiac-arrest false alarms. test2 is the headline — it is the
only set nothing was tuned on.

**Fill in this table in `EXPERIMENT_LOG.md`:**

| | Precision | Recall | F1 | Exact | CPA |
|---|---|---|---|---|---|
| test2 — Stage B | | | | | |
| test2 — original checker | | | | | |
| test2 — fine-tuned checker | | | | | |
| 52 — Stage B | 0.961 | 0.925 | 0.942 | 46/52 | 0 |
| 52 — fine-tuned checker | | | | | |
| probe — Stage B | 0.800 | 0.889 | 0.842 | 37/43 | 0 |
| probe — fine-tuned checker | | | | | |

Then **read Part 3** — every disagreement — before calling anything a failure. And specifically check
the three weaknesses: does choking separate now? Are lookalikes rejected? Are time words handled?

| Result | Next |
|---|---|
| Beats Stage B on test2 and the 52, CPA 0 | Candidate to replace Stage B in the app — a separate change |
| Better than the original checker, still not beating Stage B | The data helped; try the hybrid again with the fine-tuned checker |
| No better than the original | The examples didn't teach the task — look at which group failed |
| Great on dev, poor on test2 | It learned our example phrasing, not the task — the known risk |

---

## Committing

**Where:** the private repo — `cd /Users/User/Desktop/kyukyu-bridge`.
**What:** the new and changed scripts, `data/nli_train_sentences.json`, `EXPERIMENT_LOG.md`.
**Not:** anything in `models/` (gitignored — large, rebuildable) or the `.nli*_cache.json` files
(gitignored — model output).
Stage with `git add <files>`, check with `git status`, then `git commit -m "<what changed>"`.
