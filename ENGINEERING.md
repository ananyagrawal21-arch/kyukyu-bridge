# Engineering — the variables

Everything before this file was design: argued, reversible, judged by reasoning. Everything after
it is engineering: you change one input on purpose, you measure one output, and the number
decides. This file lists what can be changed, what can be measured, and what is not yet
measurable.

**The protocol** (from the Stage B review, and it applies to everything below):
one change per run · frozen sets stay frozen · never tune on the set you use as proof ·
record the backend · report four numbers, not one · any CPA false positive fails the run.

---

## A. Classification — instrumented, ready to use

The harness exists. These can be measured today.

| input you change | output you measure | how |
|---|---|---|
| Stage B prompt wording | precision, recall, F1, CPA-FP, per stage | `benchmark/harness.py` |
| gates on/off (negation, lexical veto) | same, plus which ids each gate removed | `benchmark/experiments.py` |
| `SLM_DISCARD` membership | same, with labels relabelled to match | `run_variant(discard=…)` |
| ontology terms added or reworded | the frozen 52 must not move | `benchmark/eval_slm.py` |
| model size (3B → distilled student) | same four numbers + latency per call | harness + timing |
| `max_new_tokens`, quantisation, backend | latency; outputs should be byte-identical | `bench_*` scripts |

**Measured so far:** baseline 52-set F1 0.942 / probe F1 0.842. Gates together: probe F1 0.873,
52-set unchanged. Glosses: worse, twice. Quote-the-evidence: much worse. All reverted except the
gates, which are not yet merged into `src/`.

---

## B. The two-way system — needs instrumenting as you build it

These are the numbers the product actually lives or dies on. **Build the measurement in from the
first commit**, not afterwards — a timestamp on every state transition costs nothing now and is
impossible to reconstruct later.

| input you change | output you measure | why it matters |
|---|---|---|
| where the model runs (phone / server) | time from "stop speaking" → data on console | the dispatch clock. FDMA's own transcripts show dispatch at 15–53s. |
| how many taps before the call starts | time from app open → 119 dialling | every second here is before anything else can happen |
| question set size and wording | round-trip: dispatcher clicks → answer back on console | if this is slow the dispatcher stops using it |
| when the CPR guide triggers | time from call connect → first compression | FDMA transcripts: 2:05–3:10 today. This is the number worth beating. |
| screen layout of the console | seconds for a Japanese reader to extract address + room + condition | a console nobody can read fast is not an improvement |
| closed questions vs free text | how often the dispatcher needs free text at all | decides whether the translation lane is needed |

**None of these have ever been measured.** Every one is a first.

---

## C. Not yet measurable — and what each is blocked on

| question | blocked on |
|---|---|
| does synthesized Japanese reach a dispatcher acoustically | two phones, a real cellular call, a Japanese listener |
| does `mixToTelephonyUplink` fire on an emergency call | a fire department's direct line (**never 119**) |
| how long a fire HQ takes to bridge its interpreter | ~20 phone calls to non-emergency lines |
| does the classifier survive real speech, not typed text | recorded audio of people describing emergencies |
| does Whisper's translate mode drop negation, and how often | non-English clips containing a denial |
| would a dispatcher act on this console | one conversation with a 消防本部 |

The last one is the highest-value and the cheapest.

---

## D. Instrumentation to build alongside the demo

Not features — the apparatus that makes everything in section B measurable.

1. **Timestamped event log** on every state transition, both ends, one clock. Written to disk.
2. **A replay harness** — feed a recorded session through the pipeline and get the same numbers.
   Without this you cannot compare two builds.
3. **A drill mode** — run the whole flow against a test number. This is simultaneously the
   rehearsal the user needs and the measurement rig you need.
4. **Per-run config capture** — model, backend, gate settings, commit hash, written into the
   result file. Two results without this are not comparable.

---

## E. The trap to avoid

Measuring what is easy instead of what decides.

Classification accuracy is easy to measure and mostly already good. Time-to-first-compression is
hard to measure and is the number that correlates with survival — 3.7% → 10.4% one-month
neurologically-intact survival with bystander CPR (令和7年版 救急・救助の現況).

If a week of work moves F1 by 0.01 and another week moves time-to-compression by thirty seconds,
they are not the same week.
