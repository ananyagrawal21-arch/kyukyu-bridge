# Session handoff — read this at the start of a new session

Last updated 2026-10-12, written before a context compaction so nothing is lost. `CLAUDE.md` points
here. Detail lives in `EXPERIMENT_LOG.md` (every experiment), `OPEN_DECISIONS.md` (decisions, see the
NEXT UP items #1–#6 and the 2026-10-12 architecture decision at the end), `BUILD_PLAN.md` (MVP
checklist), `POSITIONING.md` (regulatory pathway, §6 reference services incl. Smart911).

---

## 1. Where things stand

- **Intel AI Global Impact Festival is over** — the project did not reach the interview stage.
  **New external targets: GENIUS Olympiad 2027 and the Davidson Fellows Scholarship.** Verify each
  one's current rules, eligibility (founder is 17) and theme fit from official sites before shaping
  work for them. Possible issue to check: GENIUS Olympiad may require an environmental theme.
- **Target architecture is DECIDED (2026-10-12): local-first, tiered, thin relay.** AI runs on the
  phone (audio never leaves it; no cloud fallback); the server only relays (auth, validation, acks,
  retries, de-dup, durable delivery, minimal audit; no inference, no persistent medical profiles);
  profile stored encrypted on the phone and sent at call time; tier 0 = profile on dial (no AI),
  tier 1 = "symptoms pending", tier 2 = confirmed symptoms (optional — dispatcher never waits for it);
  delivery states processed / sent / acknowledged-by-destination; weak phones → tier 0 + tap picker.
  The laptop stands in for the phone in the MVP. Full text: end of `OPEN_DECISIONS.md`.
- **The README** (public, rewritten 2026-10-07) describes the new architecture honestly: what is
  built vs designed, test2 as the headline number, failed ideas, corrections to the demo video. It
  predates the local-first decision and the NLI-8 result — update it when those land in code.

## 2. The classifier — current best pipeline

`Whisper → Stage A (Qwen2.5-3B, llama.cpp Q4_K_M — was OpenVINO INT8: propose, recall) → fine-tuned NLI checker
(mDeBERTa-v3, models/nli-mdeberta-ft-ov-int8, keep if entailment ≥ 0.30: precision)`.
- **NLI-8 met its pre-registered criterion** (beat Stage B F1 on test2 and the 52, 0 false alarms):
  test2 F1 0.883 vs Stage B 0.861 (27/34 vs 25/34); 52 0.972 vs 0.942; probe 0.880 vs 0.842; CPA 0
  everywhere. Not statistically significant (11 vs 6 case wins, p=0.33) — claim "meets the
  criterion with consistent gains", never "proven better". INT8 vs fp32: 0 of 215 decisions flipped
  → ship INT8 (303 MB).
- **The checker replaces Stage B and IS wired into the app (2026-10-12)** — `src/nli_checker.py`;
  Stage A now runs on llama.cpp Q4_K_M in the app. test2 with this exact pipeline: F1 0.900
  (P 0.923, R 0.878), 0 CPA (T2-L). The app's `classify()` reproduces the tested answers 41/41.
- **Founder's mechanism, keep it:** Stage A's only job = recall; checker's only job = precision.
  Error budget (2026-10-12): 50% of remaining errors are Stage A never proposing a symptom (2/3 on
  unseen sets). Next: raise Stage A recall without tuning on the 52 / probe / test2.

## 3. Runtime tests R1–R3 — DONE 2026-10-12 (results: end of `EXPERIMENT_LOG.md`)

**Result:** R1 (llama.cpp Q8_0) and R2 (llama.cpp Q4_K_M, 2.1 GB) both PASS the switch rule — Stage A
recall no lower on 52/probe/dev, pipeline CPA 0, F1 no lower (gains of 1–2 symptoms: "no worse", not
"better"). R3: ONNX Runtime fp32 reproduces the checker exactly (0/215 flips); ONNX Runtime INT8
flips 20–23 → the checker's compressed phone format is still open. Speed on this Mac, Stage A per
sentence: OpenVINO CPU 12.5 s; llama.cpp CPU 7.1 s (0.57 s with prompt reuse); llama.cpp GPU 0.22–0.34 s
with prompt reuse. Not yet done: test2 with llama.cpp, Whisper on whisper.cpp, any real phone.
Founder approved: the app switched Stage A to llama.cpp, and test2 was run once (T2-L: PASS, F1
0.900 vs 0.883). Done together with wiring in the checker — see EXPERIMENT_LOG.md "APP CHANGE".

**R3b (2026-10-12): ONNX Runtime weight-only 8-bit FAILED** — 1/273 flipped, and its tool cannot
compress the embedding table (921 MB). Phone-ready today: ONNX Runtime fp32 (1.1 GB, exact).
Checker compression paused until after the architecture discussion (it may retrain/re-scope the
checker). `.venv311` (Python 3.11, gitignored) = export tools only; the app stays on `.venv`.

Original plan, kept for the record:

Founder asked: is OpenVINO really the best option, now that the AI runs on the phone? Answer:
for phones, no (no official Android build, no access to phone NPUs). Founder approved the installs
and downloads below and asked Claude to run the tests and report a verdict.
- **R1** runtime only: OpenVINO INT8 → llama.cpp Q8_0 (Stage A). **R2** compression only: Q8_0 →
  Q4_K_M (~2 GB, phone-sized). **R3** checker: OpenVINO INT8 → ONNX Runtime INT8 (bar: 0 of 215
  decisions flipped). Sentences: 52 + probe + dev (136, OpenVINO Stage A results already cached).
  **test2 stays untouched.** Also measure speed per call on the Mac, with and without llama.cpp's
  saved prompt state (its version of prefix caching).
- **Switch rule (set before results):** switch to llama.cpp if Stage A recall is no lower than
  OpenVINO's, full pipeline CPA 0, F1 no lower. Checker: 0 flipped decisions. If R2 loses recall,
  the phone uses Q8 and the size target waits.
- Installs/downloads approved: `llama-cpp-python` (Metal build), `onnxruntime`,
  Qwen/Qwen2.5-3B-Instruct-GGUF Q8_0 (~3.3 GB) and Q4_K_M (~2 GB) from Qwen's official HF repo.
- Phone-runtime recommendation if it passes: llama.cpp (Qwen) + whisper.cpp (Whisper) + ONNX Runtime
  Mobile (checker) on both platforms; platform-specific engines (WhisperKit, ExecuTorch-NPU) only if
  a real phone misses its latency threshold. Check `EXPERIMENT_LOG.md` for whether R1–R3 finished.

## 4. Experiments queued (in `EXPERIMENT_LOG.md`)

1. **test3** — written by the FOUNDER (no AI), ~40 sentences, without looking at training data;
   locked with a SHA-256 before use. It is the generalization judge (all other sets were written by
   Claude). Founder has no other human authors available.
2. **Stage A recall** — baseline on a development pool (dev v2 + the 287 training sentences, ~330);
   one change: recall-first prompt; LoRA fine-tune only if needed. Success: Stage A recall ≥ 98% on
   the pool, pipeline CPA 0 and precision no worse; confirmed once on test3.
3. **Smaller Stage A** (Qwen 1.5B, judged by recall — the checker now handles fabrications).
4. **Seed check** — retrain the checker with 3 seeds; is F1 0.883 stable?
5. Later, with the MVP: end-to-end with real voices (Whisper in the loop).
Known checker weaknesses: everyday dizziness/vomiting paraphrases ("room is spinning", "brought up
everything"), the over-specific "fall … on flat ground" hypothesis, over-eager "confused"; training
data is only 6% contradiction pairs.

## 5. The MVP (Track A in `BUILD_PLAN.md`)

Built: `src/session_store.py` (relay + event log, 11 tests), `src/messages.py` (message builders with
a provenance check that refuses Japanese not from the ontology, 8 tests). **Founder approved UI
changes** ("Sure you can make the UI changes") with Claude's three recommendations: remove the two
Japanese-audio screens (`dispatch_now`, `briefing`) from the flow but keep the code; show the
caller's raw words small and untranslated on the console; Japanese console with an English toggle.
**Now also required:** the three tiers, acknowledgements and delivery states, a "no reliable result"
state. Not started: the console page, the speak-then-dial caller flow, questions back, CPR guide.
Speak-then-dial is decided (founder): record first (optional, "Call now" always visible), then the
dialer opens with 119 (Android blocks apps from placing emergency calls; iOS asks to confirm).
`.streamlit/config.toml` binds to localhost — a phone can't reach it until that changes (HTTPS too).

## 6. Architecture upgrades — discussion pending (`OPEN_DECISIONS.md` #6)

External review analysed 2026-10-11: tiered delivery (adopted — now part of the decided
architecture), event sourcing with SQLite WAL + crash test proving 0 lost messages, FDMA S3-01 adapter
+ conformance tests (first get the S3-01 spec itself), OpenVINO Model Server for concurrency
(largely moot now that inference is on the phone), zero-copy (rejected — not where time goes).
The founder wants a deep discussion of upgrades next, after R1–R3.

## 7. Repo and git facts

- Push ONLY from `/Users/User/Desktop/kyukyu-bridge`. `kyukyu-public` is stale and points at the SAME
  GitHub repo (`ananyagrawal21-arch/kyukyu-bridge`, public, MIT). Never push from it.
- Privacy scrub done 2026-10-07 (ward, street, school, room removed from all current files; example
  profile now uses the Tokyo Metropolitan Government Building address). **Git history still has the
  old example address.** Founder has not yet said whether it is real — if real, history must be
  rewritten (`git filter-repo` + force-push); ask before doing anything.
- `AGENTS.md` (untracked) is a copy of `CLAUDE.md` for Cursor — keep in sync; founder decides
  whether to commit it.
- Python is `.venv/bin/python` (3.9.6). Mac is Apple Silicon (OpenVINO prefix caching unavailable
  here; Stage A with OpenVINO measured 12.5 s/sentence median on this Mac's CPU, 2026-10-12).
- Scripts that call `slm_classify` directly must set `SLM_OV_DIR` (harness.py does it), or it
  silently loads plain PyTorch.
- Locked test2 SHA-256: `b421ab3f3e41165da446a67a89f5cc370a20881f50a65fc67f665ec6499fdd33`.

## 8. How the founder wants to work (also in memory)

- Founder is the architect and wants real control: explain clearly and COMPLETELY in plain
  language — not half-explanations; re-explain from the start when asked. Code can be written for
  them, but every line must be explainable; they run things themselves in Cursor when they can.
- Give git commands with full explanation (folder, each file, each command). Never run git
  add/commit/push yourself.
- Log every experiment step and result in `EXPERIMENT_LOG.md`, failures included.
- Realism rule: every test or training sentence must be something a real caller would say at the
  start of a 119 call. Target failure TYPES, never copy failure SENTENCES. One change per run.
  Never tune on the 52, the probe or test2. Pre-register success criteria before running.
- Push back with evidence when a premise is wrong; don't negotiate or offer watered-down options;
  don't switch paths mid-experiment without saying so.

---

## 9. Where the last session ended (2026-10-12, late) — START HERE

**Done and logged (EXPERIMENT_LOG.md has the detail):**
- R1/R2: llama.cpp Q8_0 and Q4_K_M pass the switch rule for Stage A. T2-L: test2 run ONCE with
  llama.cpp Q4_K_M + fine-tuned checker → P 0.923, R 0.878, **F1 0.900**, 0 CPA false alarms (OpenVINO
  setup: 0.883). Claim is "no worse", not "better".
- **The app now runs Stage A on llama.cpp Q4_K_M and the fine-tuned NLI checker (`src/nli_checker.py`)
  instead of Stage B.** `classify()` reproduces the tested answers 41/41. `harness.py` stays on
  OpenVINO so its caches never mix runtimes. `KYUKYU_SECOND_PASS=stage_b` reproduces old benchmarks.
- R3b: ONNX Runtime weight-only 8-bit checker FAILED (1/273 flips; tool can't compress the embedding
  table → 921 MB). ONNX fp32 (1.1 GB) is exact. **Checker compression paused** until the architecture
  is decided (it may be retrained or re-scoped). `.venv311` = Python 3.11 export tools only.
- Whisper-on-phone: deliberately on hold (founder: finish text classification first).
- README (private): dated update box at the top + stale headings fixed. Founder edits the PUBLIC copy.
  A full rewrite waits for the final architecture. RESPONSIBLE_AI.md numbers corrected (old
  "precision 1.00" was the old Stage B).
- Founder's rule for now: **only bare necessities; do NOT run experiments that tune or measure the
  current 28-symptom list** (test3, Stage A recall experiment, seed check, 1.5B test are HELD) until
  the architecture discussion is done.

**Possibly uncommitted:** the founder types all git commands. Commands were given for: (1) runtime tests
+ notes, (2) app change (src/nli_checker.py, slm_classify.py, app.py, harness.py, requirements.txt,
RESPONSIBLE_AI.md), (3) R3b (onnx_weightonly_test.py, .gitignore, logs), (4) README.md. Run
`git status` to see what the founder has not yet committed; do not run git add/commit/push.

**NEXT: the architecture discussion (OPEN_DECISIONS.md #4 classifier limits, #6 delivery).** Claude's
proposal, awaiting the founder's yes/no: start with the **gap study (4c)** — read the official
緊急度判定プロトコル Ver.1「119番通報」 (see OPEN_DECISIONS.md) and FDMA's published 口頭指導 case
transcripts, list every fact a dispatcher actually uses, check what profile + symptom list + answers can
carry, and produce ranked gaps. No code, no experiments, test2 untouched.
Claude's stated view, to keep unless the founder disagrees with reasons:
- The closed, human-verified list is the CORE SAFETY PROPERTY (the AI never writes Japanese that
  reaches a dispatcher; also the answer to FDMA's 2017 doubt about AI-written text). Do not replace it
  with free generation. Weight comes from measured safety + an explained design, not vocabulary.
- The real upgrade = a **structured form** the AI fills, every field limited to verified choices
  (symptom; status ongoing/stopped; onset just now/minutes/about an hour/earlier today; side), with
  Japanese built from pre-checked pieces. The checker can verify each field like it verifies symptoms.
  The fields should come from the official protocol and the gap study, not from guessing.
- #6 (tiers, acks, crash recovery, FDMA S3-01 adapter) is about delivery and does not conflict; discuss after.
- Other open classifier items: self-corrections ("stomach… oh sorry, headache" → lost), out-of-coverage
  → "no reliable result" state, Whisper's translate mode loses negation (a reason the checker might
  eventually read the caller's own language — which is why dictionary trimming was NOT done).

**Pending side items:** a spawned task card "Fix failing room_to_kana unit test" (tests/test_speak.py;
pre-existing since commit 89a6cfa; unrelated; the function may be unused now) — the founder may or may
not start it. Open: verify GENIUS/Davidson rules and eligibility; privacy/APPI question; whether the old
example address in git history is real (ask before any history rewrite).
