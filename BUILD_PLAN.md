# Build plan — the competition MVP

Written 2026-10-03. The checklist from here to a demo a judge can watch. Tick items as they land.
Decisions and their reasons live in `OPEN_DECISIONS.md`; this file is only *what* and *in what order*.

**MVP = one complete two-way drill:** caller's phone → Intel server running OpenVINO → dispatcher
console → dispatcher asks a question → caller answers → CPR guide starts → crew handoff screen,
with the times measured.

**Scope decisions (founder, 2026-10-03):**
- **English end to end first.** The demo scenario is in English. Other languages later — speech in
  other languages already passes through Whisper, but it is not the showcase.
- **The demo runs on the Intel laptop**, at least for the competition. The fast classifier path
  (OpenVINO GenAI prefix caching) only exists on x64.
- **Demos use `data/profile.example.json`**, never the real profile. The real address must never
  appear on a judge's screen or in a recording.

---

## Track A — the loop (main focus)

- [x] A1. Session store + event log — `src/session_store.py`, 11 tests
- [x] A2. Message builders with the ontology provenance check — `src/messages.py`, 8 tests
- [ ] A3. Shared store between the caller page and the console page
- [ ] A4. **Caller flow, speak-then-dial** — needs "make UI changes"
- [ ] A5. **Console page** (`/console`) — Japanese, with a "Show English" toggle for judges
- [ ] A6. Event logging on every screen
- [ ] A7. Questions back: `data/questions.json` (drafted from 緊急度判定プロトコル, **founder verifies**)
      → console buttons → caller answers → situation updates
- [ ] A8. CPR guide: dispatcher command → caller screen with steps and a 110/min beat
      (**founder verifies the instruction text**)
- [ ] A9. Measurement script: session logs → the `ENGINEERING.md` §B times
- [ ] A10. Run the whole thing on the Intel laptop
- [ ] A11. Phone microphone over WiFi (needs HTTPS) — postponed "step 0"
- [ ] A12. Pick and script the demo scenario (English). Build A4–A8 around it.
- [ ] A13. Full rehearsal drill, timed; then one with a non-Japanese speaker

**Open UI decisions** (recommendations, awaiting founder): remove the two Japanese-audio screens
from the flow (keep the code); show the caller's raw words on the console, small and untranslated
(PROTOCOL.md question 1); Japanese console with English toggle.

## Track B — quality (measure first, then fix; one change per run)

- [x] B1. **Classifier error analysis.** (first pass 2026-10-03, `benchmark/error_analysis.py`) Every miss — 52-set on INT8, the probe, the
      self-correction case — traced to where it failed: Whisper translation, Stage A never
      proposing it, Stage B removing it, or `SLM_DISCARD`. Group by cause; fix the biggest group.
- [ ] B2. Self-correction test group (OPEN_DECISIONS 4d) — written BEFORE any fix.
- [ ] B3. Latency per stage on the Intel laptop: Whisper transcribe, Whisper translate (twice for
      non-English callers), Stage A, Stage B, end to end.
- [ ] B4. Latency fixes: get OpenVINO Whisper working (blocked by a `TypeError` with the
      anti-hallucination settings — try OpenVINO GenAI's own Whisper pipeline); overlap processing
      with the ringing phone; check whether the two Whisper passes can become one.
- [ ] B6. **Coverage: add the missing emergencies** — fracture, turning blue (cyanosis), poisoning,
      allergic reaction, burns, childbirth (the probe's out-of-coverage group, which today gives the
      dispatcher NOTHING), plus any the 緊急度判定プロトコル shows are common. Founder raised
      2026-10-05. **Only AFTER the Stage B experiment** — adding symptoms changes Stage A's menu,
      makes the saved results stale, and shifts every score (29→31 cost points across the board).
      Needs: verified Japanese per term, a new test set (the probe stays frozen), one measured run.
- [ ] B5. STT accuracy: word error rate per language on the L2-ARCTIC clips, then a bigger Whisper.

**B1 result (cached INT8 outputs, 52-set + probe, English text):** 7 misses, 8 fabrications.
- **Biggest miss cause: Stage B throws away correct answers — 5 of 7 misses**, all plain
  paraphrases ("convulsing" → seizure, "boiling hot" → high_fever, "underwater" → drowning,
  "sweating coldly" → cold_sweat, "lower back has gone" → lower_back_pain). Every 52-set miss is this.
- Stage A never proposed it: 2 (both probe).
- Fabrications: 3 of 8 are negation/time ("seizure last month but nothing today", "chest was
  hurting earlier but it stopped", "did not hit his head") — what the unmerged negation gate targets.
- **Stage B also saved 22 wrong answers, including all 5 cardiac-arrest false positives.** So B
  cannot simply be loosened. Next: read B's prompt and reasoning on the 5 rejected paraphrases.

**B1 root cause CONFIRMED by experiment (2026-10-04, `benchmark/b_isolation.py`, INT8):** the same
candidates, same statements, judged alone instead of together on a list:
    correct kept:  89% together -> 100% alone   (all 5 misses recovered)
    wrong kept:    17% together ->  57% alone   (including 2 x no_pulse = cardiac-arrest false alarms)
All 17 verdict changes went the same way (rejected together -> kept alone). Stage B is a RELATIVE
judge ("which of these fits best?"), not an absolute one ("is this true?"). A prompt can only move
its strictness; it cannot make it judge truth. That is why prompt fixes kept trading one error for
another. Next: replace B's yes/no with a SCORE per candidate and a measured threshold (see
OPEN_DECISIONS 4e for the method options). Needs a new dev set — never tune on the 52 or the probe.

## Housekeeping (any time, independent)

- [x] README corrected (backend-labelled results, withdrawn claims, redesign section, MIT)
- [x] Copy the corrected README to `kyukyu-public` (2026-10-03)
- [ ] Copy the new files (`src/session_store.py`, `src/messages.py`, tests, `benchmark/error_analysis.py`) to `kyukyu-public`
- [ ] **Fix the GitHub remotes:** `kyukyu-bridge` and `kyukyu-public` both push to
      `ananyagrawal21-arch/kyukyu-bridge`. The public copy needs its own repository before anything
      is pushed from it, or it overwrites the private one.
- [ ] Founder verifies the 27 condition terms (`verified: 0` → 1)
- [ ] Fix or update `tests/test_speak.py` (`room_to_kana("101号室")` — founder's test)
- [ ] Find out the format of the next competition stage (live demo, video, Q&A)

## Parked — after the MVP (see OPEN_DECISIONS.md NEXT UP)

Privacy and data-controller design (#1) · first installation and pilot target (#2, #5) ·
reliability vs coverage, department trust, information loss, self-corrections (#4a–4d) ·
caller UI in other languages · icons during the call · auto-stop recording.
