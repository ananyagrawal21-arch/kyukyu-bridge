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
