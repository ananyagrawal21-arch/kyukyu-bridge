# Experiment log — the classifier

A dated record of every experiment on the classifier: what was changed, why, on which backend,
what came out, and what it meant. Failures and fixes are kept on purpose. Newest entries at the
bottom. Method and rules: `EXPERIMENT_GUIDE.md`. Decisions: `OPEN_DECISIONS.md` (4a–4e).

**Current objective (one at a time):** find the best Stage B — the step that decides which of
Stage A's proposed symptoms to keep.

---

## Baseline — the numbers to beat

OpenVINO INT8 (optimum-intel), scored by `benchmark/harness.py` from the saved Stage A/B outputs.

| | Precision | Recall | F1 | Exact | CPA false alarms |
|---|---|---|---|---|---|
| 52 — Stage A only | 0.855 | 1.000 | 0.922 | 43/52 | 0 |
| 52 — A + B (ships) | 0.961 | 0.925 | 0.942 | 46/52 | 0 |
| probe — Stage A only | 0.543 | 0.926 | 0.685 | 24/43 | 5 |
| probe — A + B (ships) | 0.800 | 0.889 | 0.842 | 37/43 | 0 |

---

## 2026-09-30 — Spot check: does it understand self-corrections?

**Why:** founder's question — "My father is having a stomach.. oh sorry headache".
**Backend:** OpenVINO INT8, optimum-intel, Apple Silicon. Five sentences, full classify().
**Result:** the founder's example returned nothing (headache lost — safe, but lost). "Leg, no wait,
her head" → head_injury (correct). Controls correct.
**Meaning:** five sentences is an anecdote, not a measurement. Logged as OPEN_DECISIONS 4d; needs
its own test group.

## 2026-10-03 — B1: where does each error come from?

**What:** `benchmark/error_analysis.py` traces every miss and wrong extra to the stage that caused it.
**Backend:** saved INT8 outputs; no model run. The saved results were checked as still valid — the
only ontology change since (Sep 19) did not touch anything the model sees.
**Result:** 7 misses, 8 wrong extras across the 52 and the probe.
- **5 of 7 misses: Stage A proposed the right symptom and Stage B deleted it.** Every miss on the
  52 is this. All plain paraphrases: "convulsing", "boiling hot", "underwater", "sweating coldly",
  "lower back has gone".
- 2 misses: Stage A never proposed it.
- 3 of 8 wrong extras involve negation or time ("seizure last month", "did not hit his head").
- Stage B also correctly removed 22 wrong proposals, **including all 5 cardiac-arrest false alarms**.
**Meaning:** Stage B is where the misses come from, but it can't simply be loosened.

## 2026-10-04 — B1b: proving why Stage B deletes correct answers

**What:** `benchmark/b_isolation.py` re-asked Stage B about every proposal from a multi-symptom
list, **one at a time**. Same sentence, same symptom, same model — only the company changed.
**Backend:** OpenVINO INT8, optimum-intel, Apple Silicon.
**Result:**

| | judged together | judged alone |
|---|---|---|
| correct proposals kept | 89% (40/45) | **100% (45/45)** |
| wrong proposals kept | 17% (5/30) | **57% (17/30)**, incl. 2 × no_pulse |

All 17 changes went one way: rejected together → kept alone.
**Meaning — the root cause:** Stage B compares proposals **against each other** ("which fits best?")
instead of against the sentence ("is this true?"). A prompt can only make it stricter or more
lenient; it cannot change what it compares against. That is why prompt fixes kept trading one error
for another.
**Decision:** stop prompt-tuning Stage B. Test a different kind of checker.

## 2026-10-05 — NLI-1: choosing and converting the candidate checker

**Candidate:** `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` — an NLI model. Given two
sentences it answers *entailment / neutral / contradiction*. 279M parameters, 100 languages.
**Why this one:** it judges each symptom against the sentence on its own (it cannot compare
proposals), it has "contradiction" built in (negation), it runs on OpenVINO — a third OpenVINO
model in the pipeline — and it is small.
**Why not the alternative** (reading Qwen's own confidence): it is the same judge with the same
blind spots; small quantised models are known to give poorly calibrated confidence.
**Conversion:** `optimum-cli export openvino … --task text-classification --weight-format int8`
→ `models/nli-mdeberta-ov-int8`, **332 MB**. Needed `sentencepiece` installed first.
**Label order** (from config): 0 = entailment, 1 = neutral, 2 = contradiction.

## 2026-10-05 — NLI-2: sanity check (`benchmark/nli_sanity.py`)

**Problem found:** the model would not load —
`CPU plug-in doesn't support If operation with dynamic rank`. This DeBERTa export contains an "if"
step whose data size is unknown until it runs, and OpenVINO's CPU engine refuses to compile it.
**Fix:** fix the input size before compiling — `reshape(1, 128)` — and pad/cut every input to
exactly 128 tokens. Verified in a scratch test first. Whether the Intel laptop needs the same fix
is untested.
**Backend:** OpenVINO INT8, Apple Silicon. Load 2.0 s.
**Result (4 pairs):**

| Caller said | Symptom | Answer | Right? |
|---|---|---|---|
| collapsed and now convulsing | seizure | neutral (entailment 0.14) | ✗ |
| boiling hot to the touch | high fever | entailment 0.86 | ✓ — Stage B got this wrong |
| seizure last month, nothing today | seizure | contradiction 0.55 | ✓ |
| did not hit his head | head injury | contradiction 0.71 | ✓ |

**Speed:** 0.033–0.062 s per pair (Stage B: ~1.5 s per call on the Intel laptop).
**Meaning:** it works and reads negation and time. Four pairs prove nothing about accuracy.
**Deliberately not done:** nothing was changed to fix "convulsing" — that would be fitting the test
to the answer.

## 2026-10-05 — NLI-3: symptom sentences and dev set drafted

**`data/nli_hypotheses.json`** — one plain sentence for each of the 28 symptoms the model can
propose, written from the same definitions Stage B uses. The seizure sentence was kept exactly as
planned before the sanity check, despite the "convulsing" miss. **Frozen once scoring starts.**
**`benchmark/dev_set.json`** — 40 new cases for choosing the cut-off only: plain 10, figurative 8,
negation 6, time 5, multi-symptom 6, cardiac-arrest traps 5. Checked: no copies of the 52 or probe,
every label a valid id. **6 labels marked unsure — awaiting the founder's decision.**
**Status:** drafted by Claude, reviewed by the founder.

## 2026-10-06 — NLI-4: founder review of sentences and labels

**Symptom sentences:** approved by the founder as written. Now frozen.
**Dev set labels — founder's decisions** (recorded per case in `founder_decision`):
- numb left hand → numbness only (numb is not weak)
- "back has seized up" → back_pain (no mention of the lower back)
- "he isn't confused, he just feels very sick" → **removed** as unrealistic; replaced with "she's not
  bleeding, but she's really struggling to breathe" → difficulty_breathing
- "the bleeding stopped about an hour ago" → **heavy_bleeding** (stopped bleeding is still reported;
  the caller selects "has stopped")
- "pale and floppy but still breathing" → pale_complexion (floppy does not imply collapsed)
- "coughing hard after eating but can still talk" → nothing; **added its pair** "she's coughing hard
  after eating" → choking
Dev set: **41 cases**, 0 unsure.

**Known risk, written down before scoring:** the approved sentences are present tense ("The person
is bleeding heavily."), so the checker may read "the bleeding stopped" as a contradiction and remove
it. If the stopped-bleeding case fails, that is the predicted cause: an NLI checker cannot tell
"stopped during this emergency" from "happened long ago".

**Method rule added (founder):** when the checker disagrees with a label, read its answer before
calling it wrong. If its reading is reasonable, the LABEL may be the error. Dev-set labels may be
corrected after review, logged here; the 52 and the probe are never edited.

## 2026-10-06 — NLI-5: Stage A's proposals on the 41 new dev cases (`benchmark/dev_stage_a.py`)

**Backend:** Qwen2.5-3B, OpenVINO INT8 (optimum-intel), Apple Silicon. Saved to `.stage_a_cache.json`.
**Result, Stage A alone:** precision 0.667, recall 0.878 (36 of 41 expected symptoms proposed),
28/41 exact, 18 wrong proposals, **2 cardiac-arrest false alarms** (no_pulse twice).

**The ceiling:** 5 expected symptoms were never proposed, so **no checker can score above recall
0.878 on the dev set** — a checker can only keep or remove.
- "his back has completely seized up" → Stage A proposed **seizure** ("seized" read as seizure), not back_pain
- "her face is drooping on one side and her arm is numb" → one_sided_weakness instead of numbness
  (a stroke pattern the model inferred; the caller said numb, not weak)
- "she sank in the pool … her skin feels icy" → missed drowning AND body_cold; proposed no_pulse,
  collapsed, cold_sweat, severe_abdominal_pain
- "she's coughing hard after eating" → nausea, vomiting; missed choking

**What the checker must now remove** (18 wrong proposals), including both no_pulse alarms:
"there's no blood, but she hit her head" → no_pulse; the pool case → no_pulse. Also time cases
("headache yesterday" → headache, "hurt his back last month" → back_pain) and lookalikes
("pounding headache" → palpitations, "cold hands" → cold_sweat + pale_complexion).

**Meaning:** on the 52, Stage A found every expected symptom (recall 1.000). On new sentences it
found 88%. Stage A has gaps too — they were just not visible on the 52. Recorded for 4a; the current
experiment stays on Stage B only.

## 2026-10-06 — NLI-6: the comparison (`benchmark/nli_score.py`, `benchmark/nli_threshold.py`)

**Backend:** Stage A/B Qwen2.5-3B OpenVINO INT8; NLI mDeBERTa OpenVINO INT8 (1×128); Apple Silicon.
162 (sentence, symptom) pairs scored. Rule tested: keep a proposal if entailment ≥ X.

**Choosing X on the dev set:** CPA false alarms were 0 at EVERY X on the dev set, so the safety
brake never applied, and "highest recall" chose the most lenient line: **X = 0.05**.

**Result — FAILS the run (cardiac-arrest rule):**

| | Precision | Recall | F1 | Exact | CPA |
|---|---|---|---|---|---|
| 52 — Stage B (today) | 0.961 | 0.925 | 0.942 | 46/52 | 0 |
| 52 — NLI, X = 0.05 | 0.898 | **1.000** | 0.946 | 46/52 | 0 |
| probe — Stage B (today) | 0.800 | 0.889 | 0.842 | 37/43 | 0 |
| probe — NLI, X = 0.05 | 0.615 | 0.889 | 0.727 | 27/43 | **3** |

**What it did better than Stage B:** recovered all 4 of Stage B's misses on the 52 (convulsing,
boiling hot, underwater, sweating coldly) and lower_back_pain on the probe; correctly REMOVED Stage
B's own fabrication "it hurts, it really hurts" → chest_pain (entailment 0.00).

**What it did worse — four patterns:**
1. **Choking cannot be separated by any single line.** Real choking scored 1.00, 0.44, 0.12; false
   choking scored 0.78 ("lips turning blue"), 0.13, 0.10. The three probe false alarms are all choking.
2. **Lookalikes accepted:** "pounding headache" → palpitations 0.93; "numb hand" → one_sided_weakness
   0.93; "back seized up" → seizure 0.93; "face drooping, speech slurred" → confused 0.89.
3. **Time inconsistent:** "headache yesterday, fine now" → headache 0.97; "hurt his back last month"
   → back_pain 1.00 (yet "seizure last month" was a contradiction in the sanity check).
4. **Hypothesis wording matters:** "she fell over but there's no bleeding" → fall 0.01, because our
   sentence adds "on flat ground", which the caller never said. The model's reasoning was sound;
   the hypothesis was too specific. The stopped-bleeding case scored 0.03 — the predicted failure.

**Key finding:** Stage B and NLI fail on DIFFERENT cases. Stage B loses paraphrases but removes
lookalikes and false alarms; NLI keeps paraphrases but admits lookalikes and false choking.

**Mistakes in our own method, recorded:**
- The X-selection rule (CPA 0 → max recall) always drives X to the minimum unless the dev set
  contains the false alarms Stage A really makes. Our dev set had no false choking proposals, so
  the brake never engaged. Dev sets must contain the traps Stage A actually falls into, and the
  rule should weigh precision, not only recall.
- **The 52 and the probe have now been seen.** Any later design is informed by these results.
  Future choices must be made on dev-set evidence, and a final claim needs fresh, unseen cases.

**Decision:** NLI does NOT replace Stage B as configured. Next candidate (separate run, chosen on
the dev set): **hybrid** — Stage B decides; NLI may only RESCUE a symptom Stage B removed, at a high
bar, and never a cardiac-arrest id. Requires running Stage B on the dev set first. Longer term:
fine-tuning the NLI model (choking, time, lookalikes).

## 2026-10-06 — NLI-7: the hybrid — design written down BEFORE any result

**Why:** NLI-6 showed the two checkers fail on different cases. Stage B removes lookalikes and every
false cardiac-arrest alarm, but throws away correct paraphrases; NLI keeps paraphrases.
**Rule:** keep everything Stage B kept, plus any symptom Stage B removed that (a) NLI scores ≥ R and
(b) is not a cardiac-arrest id (no_pulse, not_breathing, choking, body_cold). The hybrid can only
add what Stage B threw away; it can never raise a cardiac-arrest alarm.
**Method fixes from NLI-6, fixed before seeing results:** R is chosen by best F1 on the dev set (not
recall alone); safety comes from rule (b), not from the line.
**Steps:** `benchmark/dev_stage_b.py` (Stage B on the 41 dev cases, same input and cache key as the
harness) → `benchmark/hybrid_threshold.py` (choose R on dev, compare once on the 52 and probe, list
every rescue as right or wrong).
**Honest caveat:** this design was motivated partly by NLI-6's results on the 52 and the probe, which
have been seen. If the hybrid wins, a final claim needs fresh, unseen cases.

## 2026-10-06 — NLI-7: the hybrid — result

**Step 1:** Stage B run on the 41 dev cases (`benchmark/dev_stage_b.py`, Qwen2.5-3B OpenVINO INT8,
same input order and cache key as the harness). **Step 2:** `benchmark/hybrid_threshold.py`.

**Choosing R on the dev set:** recall was **0.854 at every R** — on the dev set, Stage B removed only
ONE correct symptom (the stopped-bleeding case, which NLI scored 0.03, as predicted). So rescuing
could only add errors, and best F1 fell at the strictest line: **R = 0.95**, i.e. rescue almost nothing.

| | Precision | Recall | F1 | Exact | CPA |
|---|---|---|---|---|---|
| dev — Stage B alone | 0.814 | 0.854 | 0.833 | 31/41 | 0 |
| dev — hybrid, R = 0.95 | 0.814 | 0.854 | 0.833 | 31/41 | 0 |
| 52 — Stage B alone | 0.961 | 0.925 | 0.942 | 46/52 | 0 |
| 52 — hybrid, R = 0.95 | 0.962 | 0.943 | 0.952 | 47/52 | 0 |
| probe — Stage B alone | 0.800 | 0.889 | 0.842 | 37/43 | 0 |
| probe — hybrid, R = 0.95 | 0.774 | 0.889 | 0.828 | 36/43 | 0 |

**Rescues:** 52 — cold_sweat for "pale and sweating coldly" (1.00), RIGHT. Probe — chest_pain for
"the part below his face and above his stomach is paining" (0.99), WRONG by the founder's earlier
judgment that this sentence is too vague (the checker's reading is defensible; the probe is frozen).

**Verdict:** a draw — one fixed, one broken; a one-case difference is within noise at this size.
CPA 0 everywhere, as designed. **Not adopted.**

**The real finding — the problem is smaller than the 52 suggested.** On the 52, Stage B removed 4
correct symptoms; on 41 unseen sentences it removed 1. Stage B's relative-judging flaw (B1b) is
real, but on new sentences it costs little. On the dev set the remaining errors are:
- **6 misses:** 5 that Stage A never proposed (no checker can fix these) + 1 removed by Stage B
  (stopped bleeding — a time problem).
- **8 wrong extras that pass BOTH stages:** time (headache "yesterday", back pain "last month"),
  lookalikes ("pounding headache" → palpitations, "numb arm" → one_sided_weakness, "cold hands" →
  cold_sweat, "coughing after eating" → nausea), over-reading ("pale and floppy" → collapsed; the
  pool case → collapsed).

**Next (still the "which guesses to keep" objective):** test the September negation gate and lexical
veto — built for time/negation errors, never merged, never tested on unseen sentences — on the dev
set. Stage A's misses are a separate objective, logged for 4a.

## 2026-10-06 — NLI-8: fine-tuning the checker — plan, written before any training

**Why this is the next step on the same path:** NLI-6/7 showed the off-the-shelf checker fails in
three specific ways — choking (real 0.12–1.00 vs false up to 0.78: no line separates them),
lookalikes (0.89–0.93 for wrong symptoms), and time words (0.97–1.00 for "yesterday", "last month",
with near-zero contradiction). No threshold or combination rule can fix a model that scores these
wrongly; the model itself has to learn them.
**Feasibility:** torch 2.8.0 with Apple GPU (MPS), 16 GB RAM, 230 GB free. `accelerate` is not
installed, so training uses a plain PyTorch loop (also easier to read line by line).
**Steps:**
1. **A fresh test set, written and locked BEFORE any training** (`benchmark/test2_set.json`). The 52
   and the probe have been seen; this gives a clean number. Never used for choosing anything.
2. Training examples aimed at the three weaknesses + negation. No overlap with the 52, the probe,
   the dev set or test2 (checked automatically). Failure TYPES may be targeted; failure SENTENCES are
   never copied.
3. Train mDeBERTa-v3-base-xnli (plain PyTorch, Apple GPU) → `models/nli-mdeberta-ft`.
4. Convert to OpenVINO INT8 with the same optimum-cli command → `models/nli-mdeberta-ft-ov-int8`.
5. Score with the same scripts; choose X on the dev set; compare once on test2, the 52 and the probe.
**Success:** beats Stage B on test2 and the 52 with ZERO cardiac-arrest false alarms.
**Known risk:** training examples are written by an AI and reviewed by the founder. The model may
learn the phrasing of the examples rather than the task — test2, written separately, is the check.

## 2026-10-06 — NLI-8 step 1: fresh test set drafted (`benchmark/test2_set.json`)

34 cases, written BEFORE any training example: plain 8, choking 5, time 5, lookalike 6, negation 4,
multi-symptom 3, cardiac-arrest traps 3. Checked automatically: every label a valid id; no exact
copies and no near-copies (>50% shared words) of the 52, the probe or the dev set — two drafts that
crossed that line were reworded before saving. 2 labels marked unsure for the founder. **Locked
once the founder approves; used only for the final report.**

## 2026-10-06 — NLI-8 step 1 (revised): test2 rewritten under the REALISM RULE

**Founder's rule:** every test sentence must be something a real caller would plausibly say at the
start of a 119 call. Testing the model on situations that never happen punishes or rewards it for
nothing. The two flagged drafts ("he's fine now", "fainted but woke up straight away") failed this,
and a re-check found 7 more that did ("sweaty after his run but otherwise fine", "neck is stiff from
sleeping badly", "fingers a bit blue from the cold weather", …).
**Change:** traps now sit INSIDE real emergencies — e.g. "she's been coughing for days and now she
has a high fever" (coughing that is not choking), "he's sweating a lot from the heat and he's very
dizzy" (sweat that is not cold sweat), "I can't tell if he's breathing, he's just lying there" (no
pulse is never stated). Still 34 cases, same groups; labels valid; no copies or near-copies.

## 2026-10-06 — test2 LOCKED; dev set v2

**test2 locked by the founder.** SHA-256 of `benchmark/test2_set.json` at lock:
`b421ab3f3e41165da446a67a89f5cc370a20881f50a65fc67f665ec6499fdd33`
Anyone can re-run `shasum -a 256 benchmark/test2_set.json` — a different value means it was edited.

**Dev set v2 (founder: apply the realism rule to the dev set too).** 5 cases replaced, same groups:
- "his hands are cold but the rest of him feels warm" → "his hands are freezing but he's burning up with a fever" (high_fever)
- "I can feel a strong pulse, he's just very sleepy" → "he's breathing but he's gone grey and won't wake up properly" (pale_complexion)
- "he had a bad headache yesterday but he's fine now" → "he had a bad headache yesterday, and today he's slurring his words" (slurred_speech)
- "my wife had a stroke years ago" → "my wife had a stroke years ago, and now she's collapsed on the floor" (collapsed)
- "she's not choking, she's just coughing a little" → "she isn't choking, but her throat is swelling up and she's struggling to breathe" (difficulty_breathing)
**NLI-6 and NLI-7 were measured on dev v1;** their results stand as recorded. From NLI-8 on, dev v2.
The 5 new cases need Stage A, Stage B and NLI scores — the existing scripts skip saved cases, so
re-running them computes only these 5.

## 2026-10-06 — NLI-8: hand-over to the founder

`FINETUNE_GUIDE.md` written: steps A–F (saved results for test2 and dev v2 → ~300 realistic training
sentences with an automatic overlap check → plain-PyTorch fine-tuning → OpenVINO INT8 conversion →
three-way comparison on test2 → decision). The founder carries it out in Cursor. Pre-registered
success: beats Stage B on test2 and the 52 on F1, with zero cardiac-arrest false alarms. The X rule
for this run is fixed in advance: zero CPA false alarms → best F1. Base model weights confirmed
cached locally (552 MB). `.gitignore` now covers every `benchmark/.nli*_cache.json`.

## 2026-10-07 — NLI-8 step A: Stage A and Stage B on test2 and dev v2

**Run by the founder in Cursor.** `dev_stage_a.py` / `dev_stage_b.py` gained a `--set dev|test2`
option (written by Cursor's AI, reviewed by the founder). Backend: Qwen2.5-3B OpenVINO INT8, Apple Silicon.

| | Precision | Recall | F1 | Exact | CPA |
|---|---|---|---|---|---|
| dev v2 — Stage A only | 0.707 | 0.891 | 0.788 | 28/41 | 2 |
| dev v2 — Stage A + B | 0.848 | 0.848 | 0.848 | 31/41 | 0 |
| **test2 — Stage A only** | 0.735 | 0.878 | 0.800 | 22/34 | 0 |
| **test2 — Stage A + B (today's app)** | **0.895** | **0.829** | **0.861** | **25/34** | **0** |

**The bar for the fine-tuned checker: F1 0.861 on test2, with 0 false alarms.**
**Ceiling:** Stage A never proposed 5 expected symptoms on test2 ("tumbled down the steps" → no
fall_down; "sweating from the heat and very dizzy" → nothing; "going to be sick" → no nausea; "mumbling
like he's drunk" → no slurred_speech; "fainted" → no collapsed). No checker can exceed recall 0.878.
**Stage B threw away 2 correct symptoms on test2:** seizure for "having a fit and foaming at the
mouth"; nausea for "lightheaded and queasy, pulse going really fast". On dev v2: heavy_bleeding (the
stopped case) and pale_complexion ("gone grey").
**Cosmetic, not fixed:** the scripts print "dev cases" even with `--set test2`, and some lines print
3 times (a library starts helper processes that re-read the script's top level).

## 2026-10-07 — NLI-8 step B: training sentences drafted (`data/nli_train_sentences.json`)

**287 sentences**, drafted by Claude: plain 108 (≈4 per symptom), choking 20, choking lookalikes 20,
lookalikes 49, time 40, negation 30, multi-symptom 20. Each has `expected` (happening now →
teaches entailment) and `denied` (ruled out or in the past → teaches contradiction). Every symptom
is expected at least 5 times (fewest: no_pulse 5, drowning 6, lower_back_pain 6).
**Leak check** — `benchmark/check_overlap.py` against all 170 test sentences (52, probe, dev v2,
test2): first draft had 8 near-copies (>50% shared words, e.g. "choking on a piece of meat" vs the
52's "choking on a piece of mochi"); all 8 reworded. Now: 0 exact copies, 0 near-copies, 0 bad
labels, 0 duplicates.
**Status:** awaiting the founder's review — all 61 choking / no_pulse / body_cold sentences in full,
and at least 1 in 5 of the rest. From here, `data/nli_train_sentences.json` itself is the source of
truth; every edit is made to that file and re-checked.

## 2026-10-07 — NLI-8 step B: founder review — training sentences APPROVED

The founder flagged 13 sentences; a re-scan for the same two patterns (fragments, and cases already
resolved) found 4 more (one misnumbered at first and corrected). **14 changed, 3 kept** (#73, #76,
#136). Old wording is kept in each sentence's `founder_review` field. The two most important:
- **#192** "she has a pulse but she's breathing very strangely" → difficulty_breathing, no_pulse
  denied. **Removed as dangerous to teach:** "breathing strangely" in a collapsed person is a classic
  sign of cardiac arrest (agonal gasping). Now "has a pulse and is awake, but breathing very fast".
- **#120** "can't get air … eating peanuts" → choking. **Ambiguous:** peanuts suggest an allergic
  reaction, not choking. Now a boiled sweet.
Also: two choking cases that ended resolved (#124, #219) now say what is still wrong; fragments
(#191, #164, #154, #181, #182) are now embedded in real emergencies; #283 changed to a different
scenario because it was conceptually a paraphrase of a dev-set failure case, even though it passed
the word check.
**Leak check after changes:** 0 exact copies, 0 near-copies, 0 bad labels, 0 duplicates. CLEAN.
**Founder: approved for training.**

## 2026-10-12 — NLI-8 step C: baseline fine-tune — trained

**Run by the founder in Cursor.** `benchmark/nli_finetune.py` (learner version, rewritten by Cursor's
AI to the founder's spec: numbered steps, KNOBS block, DRY_RUN flag; same behaviour as the first
version). Knobs at defaults: 3 epochs, lr 2e-5, batch 8, weight decay 0.01, 3 neutrals per
sentence, 10% held back by SENTENCE, seed 42. Device: Apple GPU (mps). Saved to
`models/nli-mdeberta-ft`.

**Pairs:** train 1,134 (entailment 295 / 26%, contradiction 65 / 6%, neutral 774 / 68%);
held-back 125 (34 / 4 / 87).

| epoch | train loss | held-back loss | held-back accuracy |
|---|---|---|---|
| 1 | 0.4479 | 0.4124 | 0.8720 |
| 2 | 0.2036 | 0.2680 | 0.9200 |
| 3 | 0.1100 | 0.2419 | 0.9360 |

**Reading:** training loss falls steadily; held-back loss is still falling at epoch 3, so it is not
yet memorising. Held-back accuracy 93.6% against a 70% floor (a model that always answers
"neutral" would score 87/125). **Limits:** the held-back set is 125 pairs in the same style as the
training data, with only 4 contradiction pairs — it shows training worked, not that the checker beats
Stage B. That is decided on test2 (step E).
**Known imbalance, not yet acted on:** contradiction is 6% of training pairs, though time/negation
is one of the three target weaknesses. Candidate follow-ups (one at a time, after step E): more
`denied` sentences, or class-weighted loss.

## 2026-10-12 — NLI-8 step D: conversion plan changed before running (founder's challenge)

The founder asked whether converting the fine-tuned checker to OpenVINO INT8 is the best move. It
is the right move for a FAIR comparison — the original checker was scored as OpenVINO INT8, so
scoring the fine-tuned one any other way would change two things at once (training AND
runtime/compression). It is not needed for speed (0.035 s per check). But INT8's effect on a
fine-tuned model was never measured, and fine-tuning moves decisions to exactly the borderline
cases where a small score shift flips an answer.
**Change, decided before conversion:** export BOTH `models/nli-mdeberta-ft-ov-int8` and
`models/nli-mdeberta-ft-ov-fp32`, score both, and compare. Same runtime and same weights — the only
difference is compression, so the gap between them is exactly what INT8 costs. Ship INT8 only if it
costs nothing measurable on test2; otherwise ship fp32 and record why.

## 2026-10-12 — NLI-8 step D: converted (founder, in Cursor)

`optimum-cli export openvino --task text-classification`, twice:
- `models/nli-mdeberta-ft-ov-int8` — NNCF int8_asym on 100% of weight layers (75/75); 303 MB
- `models/nli-mdeberta-ft-ov-fp32` — uncompressed; 1.1 GB
INT8 is ~3.6× smaller. Whether it costs accuracy is measured in step E (fp32 vs INT8 on the same
runtime). The "`loss_type=None` … ForCausalLMLoss" message is a leftover training-config note and does
not affect inference.

## 2026-10-12 — NLI-8 step E1: scoring scripts extended (Claude, Cursor limit reached)

- `benchmark/nli_score.py`: `--model-dir` (default `models/nli-mdeberta-ov-int8`) and `--cache`
  (default `benchmark/.nli_cache.json`); test2 sentences added to `all_sentences()`. With no options
  it behaves exactly as before.
- `benchmark/nli_threshold.py`: `--cache` (default as before); test2 added to PART 2 and PART 3.
  **X rule changed from "zero CPA → best recall" to "zero CPA → best F1"** — the method fix recorded
  in NLI-6/7, decided before any fine-tuned result was seen. The original checker is re-run under the
  same rule, so all three checkers are judged identically.
- `hybrid_threshold.py` still imports cleanly (it reads the default scores at import time).

## 2026-10-12 — NLI-8 step E2/F: RESULT — the fine-tuned checker meets the pre-registered criterion

**Run by the founder.** All three checkers judged identically: X chosen on dev v2 by "zero CPA → best
F1"; compared once on the 52, the probe and test2. test2 fingerprint re-checked after the run:
unchanged (`b421ab3f…fdd33`). Backend: OpenVINO, Apple Silicon.

| | Precision | Recall | F1 | Exact | CPA |
|---|---|---|---|---|---|
| **test2 — Stage B (today)** | 0.895 | 0.829 | 0.861 | 25/34 | 0 |
| test2 — original checker (X=0.20) | 0.846 | 0.805 | 0.825 | 24/34 | 0 |
| **test2 — fine-tuned, INT8 (X=0.30)** | **0.944** | **0.829** | **0.883** | **27/34** | **0** |
| 52 — Stage B | 0.961 | 0.925 | 0.942 | 46/52 | 0 |
| 52 — fine-tuned, INT8 | 0.946 | 1.000 | 0.972 | 49/52 | 0 |
| probe — Stage B | 0.800 | 0.889 | 0.842 | 37/43 | 0 |
| probe — original checker | 0.719 | 0.852 | 0.780 | 32/43 | **1** (fails) |
| probe — fine-tuned, INT8 | 0.957 | 0.815 | 0.880 | 37/43 | 0 |

**Pre-registered criterion — beat Stage B's F1 on test2 and the 52 with zero false cardiac-arrest
alarms: MET** (test2 0.883 vs 0.861; 52 0.972 vs 0.942; CPA 0 on every set).

**INT8 vs fp32:** identical results on all three sets. Largest score difference 0.045; **0 of 215
decisions flipped** at X=0.30. Per the rule set before conversion: **ship INT8** (303 MB vs 1.1 GB).
Speed on Apple Silicon: 0.032 vs 0.033 s per pair.

**What the fine-tuning fixed (the three target weaknesses):**
- **Choking now separates cleanly.** Real choking: 1.00, 1.00, 0.96–0.97, 1.00, 1.00. False choking:
  "lips turning blue" 0.78 → **0.00**; "thought she was choking but she wasn't" 0.13 → 0.01.
  (Before: real 0.12–1.00, false up to 0.78 — no line could separate them.)
- **Time words:** "seizure last month but nothing today" 0.01, "chest was hurting earlier but it
  stopped" 0.08, "chest pain last week" 0.00, "dizziness went away" 0.00 — all removed (Stage B kept
  several of these).
- **Lookalikes:** "numb hand" → one_sided_weakness 0.93 → 0.19; "pounding headache" → palpitations
  no longer kept.

**What it still gets wrong:**
- **Lost recall on everyday paraphrases:** "the room is spinning" → dizziness 0.13; "lightheaded" →
  dizziness 0.09; "brought up everything she ate" → vomiting 0.06. Probe recall fell 0.889 → 0.815.
- **"she fell over but there is no bleeding"** → fall 0.05: the hypothesis "fell over ON FLAT
  GROUND" adds detail the caller never said (first seen in NLI-6; hypotheses are frozen).
- **Over-keeps:** "he doesn't look right at all" → confused 0.95; "threw up earlier, head killing
  him" → seizure 0.73; "face drooping and speech slurred" → confused 0.41.

**Honest strength of the evidence:** cases only one checker got exactly right — 52: fine-tuned 4,
Stage B 1; probe: 4 vs 4; test2: 3 vs 1; all three: **11 vs 6, two-sided sign test p = 0.33.** The
direction is consistent across three independent sets and the safety-critical behaviour (choking,
time, 0 false alarms) changed qualitatively, but at this sample size the overall difference is
**not statistically significant**. Claim it as "meets the pre-registered criterion with consistent
gains", never as "proven better". The probe was seen before the training data was written, so its
gain is partly by design; test2 is the clean number.

**Decision:** the fine-tuned INT8 checker becomes the **candidate to replace Stage B** in the app —
as a separate, logged change. Its own improvement runs come after (one at a time): everyday
dizziness/vomiting paraphrases, the over-specific "fall" hypothesis, over-eager "confused"; plus the
known 6% contradiction imbalance.

## 2026-10-12 — Error budget of the new pipeline (Stage A + fine-tuned checker, X=0.30)

Analysis only, from saved results — no new test run.

| set | expected | Stage A never proposed | checker removed correct | wrong extras kept |
|---|---|---|---|---|
| 52 | 53 | 0 | 0 | 3 |
| probe | 27 | 2 | 3 | 1 |
| dev | 46 | 5 | 0 | 1 |
| test2 | 41 | 5 | 2 | 2 |
| **total** | **167** | **12 (50% of errors)** | **5 (21%)** | **7 (29%)** |

On the two sets never used in development of Stage A (dev, test2): Stage A misses 10 of 87 expected
symptoms — **2/3 of the remaining errors.** The checker can only keep or remove, so **Stage A, not
the checker, is now the main limit.** The "two filters" are not two independent chances to catch an
error: recall is capped by the proposer; the checker only controls precision.

## 2026-10-12 — NEXT (planned, not run): Stage A recall — keeping the original mechanism

**Founder's decision:** keep the backbone. Stage A's only job is to miss nothing; the checker's only
job is to remove what is wrong. Neither trades precision against recall. (The earlier prompt-tuning
loop happened because the old Stage B was asked to do both.) Claude's "checker scores all 28
symptoms" idea is dropped. Tuning rule: never on the 52, the probe or test2.
**Plan:** (1) test3 — written by real people, not AI, locked; the final judge. (2) Baseline Stage A
recall on a fresh development pool: dev v2 (41) + the 287 training sentences (never seen by Stage A)
≈ 330 sentences; run on the Intel laptop. (3) One change: a recall-first Stage A prompt ("list every
symptom that could apply; extra is fine"); measure Stage A recall, proposals per sentence, and the
full pipeline (precision, F1, CPA). (4) Only if recall is still short: LoRA fine-tune of Stage A on
the 287 sentences (OpenVINO GenAI loads LoRA adapters). (5) Judge the winner once on test3.
**Pre-registered success:** Stage A recall ≥ 98% on the development pool; full pipeline CPA 0 and
precision no worse than today; confirmed on test3.

## 2026-10-12 — R1–R3 runtime tests: STARTED (founder approved; Claude runs them)

Pre-registered (see HANDOFF.md §3): R1 OpenVINO INT8 → llama.cpp Q8_0 (Stage A, runtime only);
R2 Q8_0 → Q4_K_M (compression only); R3 checker OpenVINO INT8 → ONNX Runtime INT8 (bar: 0 of the
scored pairs flipped at X=0.30). Sentences: 52 + probe + dev; test2 untouched. Switch rule: Stage A
recall no lower, pipeline CPA 0, F1 no lower.
**How to resume if interrupted:**
- installs: `CMAKE_ARGS="-DGGML_METAL=on" .venv/bin/pip install llama-cpp-python onnxruntime`
- GGUFs from `Qwen/Qwen2.5-3B-Instruct-GGUF` into `models/gguf/` (gitignored under `models/`)
- `.venv/bin/python benchmark/runtime_test.py --gguf models/gguf/<q8_0 file> --tag q8` (R1)
- `.venv/bin/python benchmark/runtime_test.py --gguf models/gguf/<q4_k_m file> --tag q4km` (R2)
- `.venv/bin/python benchmark/onnx_checker_test.py` (R3)
Stage A results cache to `benchmark/.stage_a_llamacpp_<tag>.json`; new checker scores are added to
`benchmark/.nli_ft_cache.json` (both gitignored).

## 2026-10-12 — R3: the checker on ONNX Runtime — partial results

Compared against the shipped OpenVINO INT8 checker on all 215 scored (sentence, symptom) pairs;
bar set beforehand: 0 decisions flipped at X = 0.30. `benchmark/onnx_checker_test.py`, onnxruntime
1.19.2 (CPU), Apple Silicon.

| ONNX version | flipped / 215 | largest score diff | size |
|---|---|---|---|
| uncompressed (fp32) | **0** | 0.036 | ~1.1 GB |
| INT8, `quantize_dynamic` defaults | 23 ❌ | 0.887 | 338 MB |
| INT8, MatMul-only, per-channel | 20 ❌ | 0.749 | 917 MB |
| half precision (fp16) | not finished — stopped after the time-box (see below) | | |

**Reading:** ONNX Runtime itself reproduces the checker exactly — the runtime is not the problem.
ONNX Runtime's INT8 tools quantize activations dynamically as well as weights, and this DeBERTa
model does not tolerate it; OpenVINO's NNCF INT8 was weight-only (int8_asym), which is why it cost
nothing. **Consequence for the phone:** the checker needs fp16 or a weight-only INT8 method, not ONNX
Runtime's default INT8. Speed: ~70 ms/pair on the Mac CPU (OpenVINO: ~32 ms).
**R3 fp16 — stopped (time-boxed).** Two converters tried: `onnxconverter_common` (first attempt gave
an invalid Cast-node model; the fixed retry was still converting after 10 min) and ONNX Runtime's
transformers converter (still converting after 20+ min, ~2 GB RAM). Likely the 250k-token embedding
table (~190M of 279M parameters). Not pursued now: the decisive finding stands (ONNX Runtime
reproduces the checker exactly; its INT8 tools do not). **Open for the phone phase:** the checker's
compressed format — candidates: fp16 via a native tool, Core ML weight-only INT8 (iOS), or ONNX
Runtime's weight-only 8-bit MatMul quantization in a newer release (needs Python ≥3.10).

## 2026-10-12 — R1 and R2: Stage A on llama.cpp — RESULTS

`benchmark/runtime_test.py`, llama-cpp-python 0.3.36 (Metal build), Apple Silicon Mac. Same messages
and parser as `src/slm_classify.py`; greedy decoding (temperature 0, top_k 1), max 32 tokens.
Compared against the saved OpenVINO INT8 Stage A results (`benchmark/.stage_a_cache.json`, made through
`harness.py`, which sets `SLM_OV_DIR` — checked, so those really are OpenVINO results). Checker = the
fine-tuned OpenVINO INT8 checker at X = 0.30 for every row, so only Stage A changes. 52 + probe + dev
(136 sentences). **test2 not touched.**

| set | Stage A | Stage A recall | pipeline P | R | F1 | exact | CPA false alarms (pipeline) |
|---|---|---|---|---|---|---|---|
| 52 | OpenVINO INT8 (2.9 GB) | 53/53 = 1.000 | 0.946 | 1.000 | 0.972 | 49/52 | 0 |
| 52 | llama.cpp Q8_0 (3.6 GB) | 53/53 = 1.000 | 0.964 | 1.000 | 0.981 | 50/52 | 0 |
| 52 | llama.cpp Q4_K_M (2.1 GB) | 53/53 = 1.000 | 0.964 | 1.000 | 0.981 | 50/52 | 0 |
| probe | OpenVINO INT8 | 25/27 = 0.926 | 0.957 | 0.815 | 0.880 | 37/43 | 0 |
| probe | llama.cpp Q8_0 | 26/27 = 0.963 | 0.958 | 0.852 | 0.902 | 38/43 | 0 |
| probe | llama.cpp Q4_K_M | 26/27 = 0.963 | 0.958 | 0.852 | 0.902 | 38/43 | 0 |
| dev | OpenVINO INT8 | 41/46 = 0.891 | 0.976 | 0.891 | 0.932 | 37/41 | 0 |
| dev | llama.cpp Q8_0 | 43/46 = 0.935 | 0.977 | 0.935 | 0.956 | 38/41 | 0 |
| dev | llama.cpp Q4_K_M | 43/46 = 0.935 | 0.956 | 0.935 | 0.945 | 37/41 | 0 |

Cardiac-arrest symptoms PROPOSED by Stage A (before the checker; all were removed by the checker in
every row): OpenVINO 0 / 5 / 2, Q8_0 0 / 2 / 3, Q4_K_M 0 / 1 / 2 (52 / probe / dev).

**R1 (OpenVINO INT8 → llama.cpp Q8_0, runtime change): PASSES the pre-registered rule.** Stage A recall
no lower on any set (equal on the 52, +1 symptom on the probe, +2 on dev); pipeline CPA 0; F1 no lower.
**R2 (Q8_0 → Q4_K_M, compression only): PASSES** — Stage A recall identical to Q8_0 on all three sets;
pipeline CPA 0. One extra kept symptom on dev ("she's talking gibberish and doesn't know where she
is": Q4 also kept `slurred_speech`; expected only `confused`), so dev F1 0.945 vs 0.956.

**Honest reading:**
- The two runtimes do NOT give identical answers: Stage A's proposals differ on 30/136 sentences
  (Q8_0) and 37/136 (Q4_K_M). They are different 8-bit/4-bit versions of the same Qwen model, so
  small differences are expected. Most differences are extra or missing wrong guesses that the
  checker then removes.
- The gains (1–2 symptoms per set) are too small to call llama.cpp "better". The claim is
  "**no worse** on the measured sets, at 2.1 GB instead of 2.9 GB".
- Q4_K_M proposes more extra symptoms than Q8_0 (more work for the checker) — the checker held.
- Not yet measured with llama.cpp: test2 (locked) and anything with real voices.

**Speed, Stage A per sentence, this Mac (median over 8 dev sentences):**

| runtime | where | prompt state reused (prefix caching) | median |
|---|---|---|---|
| OpenVINO INT8 (optimum-intel) | CPU | not available on ARM Macs | 12.48 s |
| llama.cpp Q8_0 | CPU only | no (reset each call) | 7.05 s |
| llama.cpp Q8_0 | CPU only | yes | 0.57 s |
| llama.cpp Q8_0 | Apple GPU (Metal) | no / yes | 1.04 s / 0.34 s |
| llama.cpp Q4_K_M | Apple GPU (Metal) | no / yes | 0.99 s / 0.22 s |

Fairness notes: OpenVINO is an Intel runtime; on an ARM Mac it has no prefix caching and is not at its
best (on the Intel laptop, 2026-08-24, OpenVINO GenAI with prefix caching measured 4.16 s). The
fair same-chip, same-job comparison is CPU vs CPU without prompt reuse: 12.48 s vs 7.05 s. Phone
speed is NOT measured — these are Mac numbers. The "~30 s/sentence" figure previously in HANDOFF.md
was not a measurement of this setup; corrected to 12.5 s.
Measurement mistake caught and corrected: the first OpenVINO timing ran without `SLM_OV_DIR`, so
`slm_classify` silently loaded plain PyTorch (65 s/sentence). Discarded; rerun with `SLM_OV_DIR` set
and the backend printed ("OpenVINO INT8 (optimum-intel)").
Unexplained: the R1 run took ~40 minutes of wall-clock time although its own per-call timings are
sub-second; R2 (same script, same sentences) took about a minute. Likely the first-ever Metal
load/compile or other load on the machine; the per-call figures above were reproduced by R2 and the
separate speed test.

**Combined R1–R3 conclusion:**
- Stage A on the phone: **llama.cpp, Q4_K_M (2.1 GB)** passes every pre-registered check so far.
- Checker on the phone: ONNX Runtime reproduces it exactly at fp32 (1.1 GB); ONNX Runtime's INT8 tools
  break it (20–23 of 215 decisions flipped). Compressed phone format still open (fp16 / Core ML
  weight-only INT8 / weight-only 8-bit MatMul).
- Not yet tested: Whisper on whisper.cpp; anything on a real phone.

## 2026-10-12 — T2-L: test2 once with llama.cpp Q4_K_M — PRE-REGISTERED (written before running)

Founder approved: (1) the app switches Stage A to llama.cpp, (2) one run of the locked test2 with it.
test2 SHA-256 checked just before: `b421ab3f…fdd33` (unchanged).
Setup: Stage A = llama.cpp Q4_K_M (2.1 GB, the phone candidate); checker = fine-tuned OpenVINO INT8
at X = 0.30 (unchanged). Compared with the same checker after OpenVINO Stage A (NLI-8: test2 F1 0.883).
**Rule (the same as R1/R2):** PASS if Stage A recall is no lower than OpenVINO's on test2, pipeline
cardiac-arrest false alarms = 0, and F1 no lower. **If it fails:** the laptop app stays on OpenVINO
and the difference is investigated before any switch. Run once; the result is reported whatever it is.

## 2026-10-12 — T2-L: test2 once with llama.cpp Q4_K_M — RESULT: PASS

`.venv/bin/python benchmark/runtime_test.py --gguf models/gguf/qwen2.5-3b-instruct-q4_k_m.gguf --tag q4km --test2`
(the `--test2` flag was added for this run; without it the script never reads test2).

| test2 (34 sentences, 41 expected symptoms) | Stage A recall | P | R | F1 | exact | CPA |
|---|---|---|---|---|---|---|
| OpenVINO INT8 Stage A + fine-tuned checker (NLI-8) | 36/41 = 0.878 | 0.944 | 0.829 | 0.883 | 27/34 | 0 |
| llama.cpp Q4_K_M Stage A + same checker | 39/41 = 0.951 | 0.923 | 0.878 | 0.900 | 28/34 | 0 |

All three conditions met (recall no lower, CPA 0, F1 no lower) → **PASS; the switch goes ahead.**
Stage A proposed no cardiac-arrest symptom on test2 with either runtime.
The four test2 sentences whose final answer changed:
- "my father tumbled down the steps outside" — OpenVINO: nothing; llama.cpp: `fall_down` ✅ (fixed a miss)
- "he's sweating a lot from the heat and he's very dizzy" — OpenVINO: nothing; llama.cpp: `dizziness` ✅
  + `high_fever` ❌ (expected only dizziness)
- "he threw up earlier, and now he says his head is killing him" — OpenVINO kept a wrong `seizure`;
  llama.cpp did not ✅
- "my son is wheezing and can't catch his breath, he has asthma" — llama.cpp also kept a wrong
  `chest_pain` ❌
Net: 3 symptoms gained or fixed, 2 new wrong ones → recall up, precision down a little. A one-case
difference in exact matches (28 vs 27) is not significant; the honest claim stays "no worse".
Note: llama.cpp's Stage A suggests MORE extra symptoms than OpenVINO (e.g. 6 for the heat sentence),
so the checker carries more of the load. The checker held (0 CPA), but this is worth watching.
Speed in this run (Mac GPU): 0.27 s per call with prompt reuse, 0.99 s without.

## 2026-10-12 — APP CHANGE: Stage A on llama.cpp + the fine-tuned checker wired in (replaces Stage B)

Founder approved switching the app's Stage A to llama.cpp after T2-L passed.
**Finding that forced the second part:** with only the runtime switched, the app still ran Stage A →
old Stage B (`_review_list`), a combination never tested on llama.cpp. First check: "my husband
clutched his chest and dropped to the floor, he's still awake" — llama.cpp Stage A proposed
`chest_pain, collapsed`; Stage B on llama.cpp threw away `chest_pain` (OpenVINO Stage A + B kept it).
The tested combination is Stage A + the checker, so the checker was wired in at the same time —
this makes the app equal the tested pipeline rather than adding an untested change.
Changes:
- `src/nli_checker.py` (new): loads `models/nli-mdeberta-ft-ov-int8` exactly as
  `benchmark/nli_score.py` does; keeps a symptom if entailment ≥ 0.30; button-only statuses pass
  through untouched; a symptom with no hypothesis is kept (recall first) with a printed warning.
- `src/slm_classify.py`: llama.cpp backend (`SLM_GGUF`), greedy, same settings as runtime_test.py;
  `classify(verify=True)` now uses the checker. `KYUKYU_SECOND_PASS=stage_b` reproduces the old
  benchmarks; Stage B is also the fallback (with a loud warning) if the checker files are missing.
  The model is closed at exit (fixes a harmless llama.cpp Metal GGML_ASSERT printed at shutdown).
- `app.py`: sets `SLM_GGUF` to the Q4_K_M file when present; OpenVINO remains the fallback.
- `benchmark/harness.py`: always OpenVINO (unsets `SLM_GGUF`) so its saved caches never mix runtimes.
- `requirements.txt`: llama-cpp-python==0.3.36 (Metal build instructions in the comment).
- `RESPONSIBLE_AI.md`: "precision 1.00" was the old Stage B on the 52 — replaced with today's
  measured numbers (52: 0.964; test2: 0.923; 0 CPA false alarms).
**Verification:** the app's own `classify()` on the 41 dev sentences = the tested pipeline's answers,
41/41 identical; median 0.57 s per sentence for Stage A + checker on this Mac (GPU). The chest-pain
sentence now gives `chest_pain`. Unit tests: 19 pass, 1 fails (`test_speak.py::test_room_to_kana`,
expects "101号室" → イチマルイチ but `room_to_kana` only converts plain digits) — pre-existing since
commit 89a6cfa, unrelated to this change.
Not yet re-measured: anything with real voices (Whisper in the loop) and the probe's panic group.

## 2026-10-12 — R3b: checker, weight-only 8-bit ONNX (option A) — PRE-REGISTERED

Founder approved option A ("bare necessities only"; architecture discussion next). Why A: it is the
same METHOD as the OpenVINO INT8 that changed 0 decisions — only the stored numbers are 8-bit, the
calculation stays full precision (ONNX Runtime's default INT8 in R3 also quantized the calculation,
which is what broke it). One file runs on Android and iOS via ONNX Runtime Mobile.
Tool: ONNX Runtime 1.31 `MatMulNBitsQuantizer`, bits=8, MatMul + Gather (the embedding table, 70%
of the parameters), block 128, asymmetric (like OpenVINO's int8_asym), compute precision unchanged.
Needs Python ≥ 3.10 → separate tool environment `.venv311` (Python 3.11.16; gitignored). The app
itself stays on `.venv` (3.9).
Step 1 (environment check): the already-exported fp32 ONNX scored in `.venv311` must again give 0
flips — proves the newer tokenizer/runtime reproduce the checker. Step 2: the 8-bit file.
**Pass line:** 0 decisions flipped at X = 0.30 over every scored pair in `.nli_ft_cache.json`
(the OpenVINO INT8 checker's scores). Any flip = fail, and the result is reported as it is.
Dictionary trimming (option C) deliberately NOT done: it would lock the checker to English before
the architecture discussion decides which language the checker reads.

## 2026-10-12 — R3b: RESULT — FAIL (option A, ONNX Runtime weight-only 8-bit)

`.venv311/bin/python benchmark/onnx_weightonly_test.py` (ONNX Runtime 1.31, Python 3.11.16).
- Step 1, fp32 in the new environment: **0 of 273 flipped** (largest difference 0.043, 47 ms/pair).
  The newer runtime + tokenizer reproduce the checker. (273 pairs now: R1/R2/T2-L added new ones.)
- Step 2, weight-only 8-bit: **1 of 273 flipped → FAIL by the pre-registered line.** Size 921 MB.
  Flipped pair (probe): "he's soaked in sweat but says he feels cold" vs "The person has a high
  fever." — OpenVINO INT8 0.243, ONNX fp32 0.286, ONNX 8-bit 0.311 → crosses 0.30 → a new wrong
  `high_fever` would be kept. Not a cardiac-arrest symptom, but the bar was 0 flips.
- **Second failure: no size win.** This ONNX Runtime quantizer refuses 8-bit for the embedding table
  ("Gather only supports 4 bits quantization"), so the 193M-parameter dictionary (70% of the model)
  stayed fp32: 921 MB vs 1,116 MB. The 8-bit GatherBlockQuantized OPERATOR exists in the runtime;
  the Python TOOL does not produce it yet.
**Reading:** there is no ready-made ONNX Runtime path that matches OpenVINO's lossless INT8 today.
What is proven: the checker runs EXACTLY on a phone runtime (ONNX Runtime fp32, 1.1 GB, 0/273).
Remaining routes, none started: (1) hand-built 8-bit embedding (uint8 table + per-row scale applied
after the lookup) + per-channel MatMul; (2) Core ML weight-only int8 (iOS only); (3) dictionary
trimming (lossless for kept tokens, but language-dependent → after the architecture decision).
**Decision proposed to the founder:** stop checker compression here. It is optimisation, not a bare
necessity, and the architecture discussion may retrain or re-scope the checker (language, richer
hypotheses), which would require re-exporting it anyway.
