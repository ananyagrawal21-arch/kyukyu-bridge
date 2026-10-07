# Fine-tuning guide — teaching the checker our task (experiment NLI-8)

Written 2026-10-06, rewritten the same day so every step says exactly who does what.

---

## What we are doing, in one paragraph

The objective is the best **Stage B** — the step that decides which of Stage A's guessed symptoms
to keep. A ready-made "meaning checker" (NLI) was tested as a replacement and failed in three
specific ways: it cannot tell real choking from false choking, it accepts lookalikes ("pounding
headache" → racing heart), and it ignores time words ("headache yesterday" → headache). No line or
combination can fix a model that scores these wrongly. So we **teach it**: show it ~300 example
sentences with the right answers and let it adjust. That is **fine-tuning**. Then we test it exactly
as before, on **test2** — the locked set it has never seen — against Stage B.

**Success (decided in advance):** beats Stage B on test2 and the 52 on F1, with **zero** false
cardiac-arrest alarms.

---

## Who does what

| Who | Where | Does |
|---|---|---|
| **You** | Cursor | run every command, review every change, decide, log |
| **Cursor's AI** | Cursor | writes the code changes in steps A, C and E, from the prompts in this guide |
| **Claude** | the other chat | writes the training sentences (step B); reviews your code, errors and results whenever you bring them |

**If anything errors or looks odd at any step: stop and bring it to Claude.** Paste the output.

---

## Before you start — once

1. Open Cursor → **File → Open Folder** → `/Users/User/Desktop/kyukyu-bridge`.
2. **Cmd+Shift+P** → "Python: Select Interpreter" → `.venv/bin/python` (Python 3.9.6).
3. Open the terminal: **Terminal → New Terminal**. Type `pwd` — it must print
   `/Users/User/Desktop/kyukyu-bridge`.
4. **Paste this into Cursor's AI chat, once, before asking it anything:**

> Read CLAUDE.md, EXPERIMENT_GUIDE.md and FINETUNE_GUIDE.md first, for context only. Do NOT start
> any step of FINETUNE_GUIDE.md on your own — wait until I paste the prompt for a specific step, and
> do only that step. Never write data/nli_train_sentences.json (that is done elsewhere). Rules for
> this whole session:
> never edit benchmark/slm_testset.json, benchmark/diagnostic_probe.json or
> benchmark/test2_set.json. Never edit data/nli_hypotheses.json. Use .venv/bin/python, never the
> system Python. Make only the change I ask for — nothing else. Before editing any file, show me the
> change and explain each new line in plain language.

---

## Step A — get Stage A's and Stage B's answers for the new sentences

**Goal:** the checker can only judge what Stage A guessed, and we compare against Stage B. Both
have to have run on **test2 (34 sentences)** and on the **5 new dev v2 sentences**.

**What you do:**

1. **Paste into Cursor's AI:**

> In benchmark/dev_stage_a.py and benchmark/dev_stage_b.py, add a command-line option `--set` using
> argparse. Allowed values: `dev` (the default) and `test2`. With `dev`, the script reads
> benchmark/dev_set.json exactly as it does now. With `test2`, it reads benchmark/test2_set.json.
> Change nothing else in either file.

2. **Review the change before accepting it.** It is right if:
   - `import argparse` is added, plus a few lines creating the `--set` option
   - the only other change is which file is opened, depending on `--set`
   - nothing else is touched
3. **Run these four, one at a time.** Wait for each to finish before the next:

```bash
.venv/bin/python benchmark/dev_stage_a.py
.venv/bin/python benchmark/dev_stage_b.py
.venv/bin/python benchmark/dev_stage_a.py --set test2
.venv/bin/python benchmark/dev_stage_b.py --set test2
```

**What you should see:**
- The first two only run the **5 new dev sentences** — the other 36 are already saved. About 2 minutes.
- The last two run **all 34 test2 sentences**. These take longest: 10–25 minutes for Stage A, a
  few minutes for Stage B.
- `dev_stage_a.py --set test2` ends with: *"Expected symptoms Stage A never proposed: N"*.

**Done when:** all four finish without a traceback.
**Log it:** add a short entry to `EXPERIMENT_LOG.md` with the N above. That's the ceiling — no
checker can find a symptom Stage A never guessed.

---

## Step B — the training sentences (Claude writes, you review)

**Goal:** ~300 realistic sentences, each with the correct answer, aimed at the three weaknesses.

**What Claude does** (in the other chat):
1. Writes `data/nli_train_sentences.json`.
2. Writes `benchmark/check_overlap.py` — proves no training sentence copies or nearly copies a
   sentence from the 52, the probe, the dev set or test2, and that every label is valid.
3. Runs the check, and only hands the file over once it prints "none" three times.

**What each sentence looks like:**

```json
{"group": "time", "transcript": "he had a seizure last year, today he's got a terrible headache",
 "expected": ["headache"], "denied": ["seizure"]}
```
- `expected` — what is happening **now**. These teach the model **"yes, this matches"**.
- `denied` — what the sentence **rules out** ("not", "no") or puts **in the past** ("last year",
  "it went away"). These teach it **"no — the opposite"**.
- The training script adds a few **lookalike** symptoms for each sentence, to teach it **"can't
  tell / not this"**.

**What you do:**
1. **Open** `data/nli_train_sentences.json` in Cursor.
2. **Read and check:**
   - **every** sentence in the `choking` groups, and every sentence labelled `no_pulse` or
     `body_cold` — these drive false alarms, so they need 100% checking
   - **at least 1 in 5** of the rest
3. For each one ask: **Would a real caller say this? Is the label right?**
4. **Tell Claude your changes**, for example: *"#57 unrealistic"*, *"#112 should also have
   dizziness"*, *"#203 denied should be empty"*. Claude edits the file and re-runs the check.
   (You can also edit it yourself in Cursor; then run
   `.venv/bin/python benchmark/check_overlap.py` and make sure it still says "none" three times.)

**Done when:** you've approved it and the check says "none" three times.
**Log it:** how many sentences you read, and how many you changed.

---

## Step C — the training

**Goal:** a script that takes the original checker and trains it on your sentences.

**What you do:**

1. **Paste into Cursor's AI:**

> Create benchmark/nli_finetune.py, a plain PyTorch training script (no Trainer, no accelerate).
> It must:
> 1. Load data/nli_train_sentences.json and data/nli_hypotheses.json (skip keys starting with "_").
> 2. Split the SENTENCES (not pairs) 90/10 into train and held-back, with random.seed(42).
> 3. Build pairs (caller sentence, hypothesis sentence, label): every id in "expected" →
>    entailment; every id in "denied" → contradiction; then up to 3 more ids → neutral, taken first
>    from this lookalike map for the expected ids, then at random, never using an id that is in
>    expected or denied:
>    headache↔palpitations; numbness↔one_sided_weakness; cold_sweat↔body_cold↔pale_complexion;
>    choking↔nausea,vomiting,difficulty_breathing; seizure↔back_pain,high_fever;
>    collapsed↔fall↔fall_down; chest_pain↔severe_abdominal_pain; back_pain↔lower_back_pain;
>    dizziness↔nausea; drowning↔body_cold.
> 4. Load MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 with
>    AutoModelForSequenceClassification and AutoTokenizer. Take label numbers from
>    model.config.label2id — do not hard-code them.
> 5. Tokenize each pair with max_length=128, padding="max_length", truncation=True.
> 6. Train on device "mps" if available, else "cpu": AdamW, lr 2e-5, weight_decay 0.01, batch size
>    8, 3 epochs, shuffled each epoch, torch.manual_seed(42).
> 7. After each epoch print: training loss, and on the held-back pairs: loss and accuracy.
> 8. Print how many pairs of each label were built, for train and held-back.
> 9. Save the model and tokenizer with save_pretrained to models/nli-mdeberta-ft.
> Add a short docstring at the top, and a comment above every block saying what it does.

2. **Review the code before running it.** Check that it has:
   - the 90/10 split **by sentence**, with seed 42
   - labels taken from `label2id`, not typed in as numbers
   - lr `2e-5`, `3` epochs, batch `8`
   - the save path `models/nli-mdeberta-ft`

   **Bring the file to Claude** if you want it checked line by line before running.
3. **Run:**

```bash
.venv/bin/python benchmark/nli_finetune.py
```

**What you should see:** the pair counts first, then one line per epoch, 3 in total. About 10–40 min.

**How to read the epoch lines:**
- **Training loss going down** → it's learning. ✅
- **Held-back accuracy going up, then levelling off** → it's learning the task. ✅
- **Training loss down but held-back loss going UP** → it's **memorising** the examples rather
  than learning. ⚠️ Bring it to Claude.
- If it errors about `mps`: put `PYTORCH_ENABLE_MPS_FALLBACK=1 ` in front of the command and run again.

**Done when:** the folder `models/nli-mdeberta-ft` exists.
**Log it:** the pair counts, the three epoch lines, the time taken.

---

## Step D — convert to OpenVINO

**Goal:** the trained checker runs on Intel's OpenVINO, like everything else.

**What you do — one command**, the same as the first conversion with new folder names:

```bash
.venv/bin/optimum-cli export openvino --model models/nli-mdeberta-ft --task text-classification --weight-format int8 models/nli-mdeberta-ft-ov-int8
```

**Check:**
```bash
ls models/nli-mdeberta-ft-ov-int8
```
You should see `openvino_model.xml`, `openvino_model.bin` and `config.json`, like last time.

**Done when:** those files exist.
**Log it:** the size of `openvino_model.bin`.

---

## Step E — score and compare

**Goal:** run the same measurement as before, now on three checkers: Stage B, the original
checker, and the fine-tuned one.

**What you do:**

1. **Paste into Cursor's AI:**

> In benchmark/nli_score.py: add argparse options --model-dir (default
> models/nli-mdeberta-ov-int8) and --cache (default benchmark/.nli_cache.json), and use them instead
> of the fixed MODEL_DIR and NLI_CACHE. In all_sentences(), also include every transcript from
> benchmark/test2_set.json.
> In benchmark/nli_threshold.py: add an argparse option --cache (default
> benchmark/.nli_cache.json) and load NLI scores from it. Add test2 (benchmark/test2_set.json) to
> PART 2 and PART 3, next to the 52 and the probe. Change choose_x so it picks: zero CPA false alarms
> first, then the best F1 (instead of the best recall); if several tie, the middle one.
> Change nothing else.

2. **Review:** the defaults must be the **old** values, so the old commands behave exactly as before.
3. **Run — the original checker first, so all three can be compared:**

```bash
.venv/bin/python benchmark/nli_score.py
.venv/bin/python benchmark/nli_threshold.py
```

4. **Then the fine-tuned checker:**

```bash
.venv/bin/python benchmark/nli_score.py --model-dir models/nli-mdeberta-ft-ov-int8 --cache benchmark/.nli_ft_cache.json
.venv/bin/python benchmark/nli_threshold.py --cache benchmark/.nli_ft_cache.json
```

**What you should see:** the same three parts as before. Part 2 now has three sets: the 52, the
probe, and test2.

**Done when:** both `nli_threshold.py` runs finish. **Bring both outputs to Claude** — we read them
together before deciding anything.

---

## Step F — decide

1. **Fill in this table** in `EXPERIMENT_LOG.md`:

| | Precision | Recall | F1 | Exact | CPA |
|---|---|---|---|---|---|
| test2 — Stage B | | | | | |
| test2 — original checker | | | | | |
| test2 — fine-tuned checker | | | | | |
| 52 — Stage B | 0.961 | 0.925 | 0.942 | 46/52 | 0 |
| 52 — fine-tuned checker | | | | | |
| probe — Stage B | 0.800 | 0.889 | 0.842 | 37/43 | 0 |
| probe — fine-tuned checker | | | | | |

2. **Read Part 3** — every disagreement — before calling anything a failure. Check the three
   weaknesses: does choking separate now? Are lookalikes rejected? Are time words handled?
3. **Decide:**

| What you see | Next |
|---|---|
| Beats Stage B on test2 and the 52, CPA 0 | Candidate to replace Stage B in the app — a separate change |
| Better than the original checker, not better than Stage B | The training helped; try the hybrid again with the fine-tuned checker |
| No better than the original checker | The examples didn't teach it — look at which group failed |
| Great on dev, poor on test2 | It learned our examples' phrasing, not the task |

**test2 is the headline number** — it's the only set nothing was ever tuned on.

---

## Commit after each step

In Cursor's terminal (already in `/Users/User/Desktop/kyukyu-bridge`):

```bash
git status                       # see what changed — green = staged, red = not yet
git add <the files you changed>  # put them on the list for the commit
git commit -m "<what changed>"   # save them, with a message saying what and why
```

**Never commit:** anything in `models/` or any `.nli*_cache.json` — git already ignores them.
