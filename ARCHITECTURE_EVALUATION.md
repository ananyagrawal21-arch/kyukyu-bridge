# Architecture evaluation — living document

Started 2026-10-13. Status: **first pass, for discussion — nothing here is decided.**
The research behind the five ideas is recorded unchanged in `OPEN_DECISIONS.md` #7.
Decisions, when made, go to `OPEN_DECISIONS.md` with reasons and revisit triggers.

---

## 0. The Japanese check (founder's question, answered from the repo)

The founder already verified all 29 Japanese terms in August 2026, reading them as finished
sentences (`OPEN_DECISIONS.md`, "Needs a Japanese speaker — ALL RESOLVED"). No outside speaker is
needed; the earlier suggestion that one was needed was wrong.

The check itself still matters, and the founder's own record shows it: reviewing finished sentences
caught a grammar bug (polite form before と言っています) and **the 脈がありません over-claim** (stating
"no pulse" as fact) — a safety bug. Building blocks add new joins, and joins are where such bugs
appear: pain/swelling take が (手首が腫れています), bleeding takes から (手首から血が出ています), a blow takes
を (頭を打ちました). One fixed pattern would produce wrong-but-understandable Japanese.
What must be checked is **meaning** (over-claims, ongoing vs stopped, left vs right, yes vs no), not
polish — a dispatcher understands slightly unnatural Japanese. The check is per **join pattern**, not
per sentence: a few dozen patterns, once, by the founder. This keeps "checked by a human" true.

## 1. Method: start from the problems, not the ideas

Starting from ideas only judges the ideas we happened to think of. Starting from problems shows which
problems nothing solves, and whether a simpler fix would do.
1. List every problem we actually have.
2. For each problem list every possible fix. To find missing ones ask: What is the simplest fix? What
   would a human professional do? How do other safety-critical fields do it? What does research say?
3. For each fix: pros, cons, key tradeoff, what it needs, simpler alternative.
4. Where we cannot tell which is better: a small experiment, pass line written first.
5. Decide with the must-rules (safe; fixes an observed problem or an FDMA/legal requirement;
   testable) and the founder's ranking. Write down why.

## 2. Problems × ideas

✅ helps · ⚠️ makes it harder · "partly" = partial

| # | Problem | L1 blocks | L2 promise | L3 ask | L4 locks | L5 tests |
|---|---|---|---|---|---|---|
| P1 | Things not on the list are lost (wrist sentence → nothing) | ✅ | | | | |
| P2 | Details lost: when, which side, stopped | ✅ | | | | |
| P3 | Self-corrections, ambiguity ("stomach… headache" → nothing) | | | ✅ | | |
| P4 | Translation flips "no response" into its opposite (measured) | | | partly | | |
| P5 | Nobody can say how often it is wrong | ⚠️ | ✅ | | | partly |
| P6 | Will dispatchers trust and act on it? | | partly | partly | partly | |
| P7 | Privacy: who holds medical data (APPI) | | | | ✅ | |
| P8 | Server: tiny liability; FDMA security rules | | | | ✅ | |
| P9 | Panicking caller, phone ringing | ⚠️ | | ⚠️ | | |
| P10 | Running on phones (size, speed) | | | | | |
| P11 | Only the founder can write test sentences | | ⚠️ | | | ⚠️ |
| P12 | Technical reputation | ✅ | ✅ | ✅ | ✅ | ✅ |

Gaps: P4 and P10 have no fix among the five (P10 is the runtime work; P4 → M5). Biggest tension:
L1 and L3 both make P9 harder.

## 3. Each idea

### L1 — Building blocks (verified controlled language)
- **Pros:** fixes P1, P2 while keeping "only checked Japanese"; answers FDMA's 2016–17 "fixed phrases
  are too limited" objection; output becomes structured fields (side, body part, when) → clearer
  console card, matches FDMA's structured JSON; the AI cannot output anything outside the phrasebook.
- **Cons:** more possible statements = more ways to be wrong (unproven); first quick test made output
  worse (AI forced to pick, no exit); caller has more to read and confirm; 52/probe/test2 are in the
  28-label format → new tests needed, checker retraining needed; joins must be checked.
- **Key tradeoff:** say more ↔ stay accurate.
- **Needs:** block list (gap study), founder's Japanese check, new test sentences, checker retraining.
- **Simpler alternative:** grow the flat list from 28 to ~80 whole sentences, each checked whole. No
  join bugs; coverage grows slowly; cannot combine details.
- **Settled by:** X1, X2.

### L2 — Proven error limit (conformal risk control)
- **Pros:** strongest answer to P5, checkable by a judge or FDMA; replaces the 0.30 line picked on 41
  sentences; separate stricter cardiac-arrest limit; model-agnostic (swap models → recalibrate, not
  retrain); produces the "unsure" group L3 needs.
- **Cons:** the promise covers calls resembling the calibration calls (founder-written ≠ real callers
  until drills); needs a few hundred labelled sentences never used for training (P11); the promise is
  on average across calls, not per call; a strict promise drops more uncertain facts → less is sent.
- **Key tradeoff:** stronger promise ↔ less information sent (softened by M2).
- **Simpler first step:** report the held-out error rate with an honest range (e.g. "4%, likely 2–9%").
- **Settled by:** X4.

### L3 — Ask the caller when unsure
- **Pros:** fixes P3; may catch some P4 flips; the human stays the final judge; extends the existing
  "ask, don't guess" rule (4 symptoms today).
- **Cons:** a panicking caller must read and tap (P9), possibly while the phone rings; questions must be
  understandable — English today, the caller's own language needs checked translations (that does need
  speakers of those languages); wrong taps under stress.
- **Key tradeoff:** fewer mistakes ↔ caller burden.
- **Alternative:** M3, the dispatcher asks.
- **Settled by:** X3.

### L4 — Locks and seals (signatures, blind relay, tamper-evident log)
- **Pros:** P7 (relay cannot read medical data); P8 (tiny liability; FDMA encryption and ≥1-year logs
  with CRYPTREC ciphers); needs no data; independent of the classifier.
- **Cons:** keys can fail in an emergency (lost/broken console key → profile unreadable — the dangerous
  direction; the voice call and an alarm must never depend on it); per-HQ key setup, rotation, backup —
  real complexity for one person; encrypted data may still count as personal data (founder's own
  earlier point) → reduces risk, does not automatically remove obligations (to check).
- **Key tradeoff:** more security ↔ risk of locking the dispatcher out.
- **Simpler alternative:** M1 replaces the seals for everyday messages.
- **Settled by:** design rule + X5.

### L5 — Tests a judge can read (CheckList-style)
- **Pros:** cheap; already our practice; makes L1–L3 measurable; can become a public test set; finds
  bugs (CheckList users found new bugs in an extensively tested commercial model).
- **Cons:** only as good as the sentences (all founder-written today); public release needs care; must
  stay locked and never tuned on.
- **Key tradeoff:** breadth ↔ founder's writing time. Not optional in practice: it is the instrument.

## 4. Ideas we were missing

- **M1 — Send codes, not Japanese.** Phone sends block codes only; the console (a 専用端末 *we* install,
  per FDMA's model — POSITIONING.md §2) holds its own checked phrasebook and builds the Japanese. A hacked
  phone can never inject Japanese. Makes L4's seals unnecessary except for phrasebook updates.
- **M2 — Back off to a more general statement.** Unsure of "left wrist deformed" → send "arm injury"
  instead of nothing. From conformal factuality (Mohri & Hashimoto), which makes outputs less specific
  until the guarantee holds. Softens L2's cost; helps P1.
- **M3 — The dispatcher asks.** The design already has pre-written questions the dispatcher taps, shown
  on the caller's phone (README). Console shows "possibly headache or stomach pain — unconfirmed"; the
  trained professional decides whether to ask. Less caller burden (P9).
- **M4 — "Something else: interpreter needed."** Out-of-coverage is shown clearly with the caller's
  language, so the dispatcher can bring in Japan's existing three-way interpretation. Hands over to it.
- **M5 — Check the caller's own words too.** The checker is built on a multilingual model; check each
  fact against the original-language transcript and the English translation; disagreement → unsure.
  Fixes P4. Whether the English-only fine-tune works in other languages is unmeasured. Waits for Whisper.
- **M6 — Measure the whole system in drills:** seconds to correct address + symptoms on the console,
  with vs without the app (already the planned impact measure, #5).
- **M7 (optional) — Independent review of the blocks' medical meaning by a paramedic (救急救命士).**
  Not for the Japanese; for credibility with FDMA and judges.
Rejected again: open machine translation to the dispatcher (breaks the core rule; FDMA's 2017 doubt).

## 5. The big tradeoffs

1. Say more ↔ stay accurate (L1) → X2.
2. Fewer mistakes ↔ caller burden (L3 vs M3) → X3.
3. Stronger promise ↔ less sent (L2), softened by M2 → X4.
4. More security ↔ locking the dispatcher out (L4) → design rule + X5.
5. Ambition ↔ time → founder's ranking and deadline.

## 6. Candidate design v2 (how it could fit together)

1. Caller speaks; the AI picks blocks, or "not said" / "something else" (L1).
2. Checker tests each block; a proven line decides keep / drop / unsure (L2); unsure → try a more
   general block (M2).
3. Still unsure → "unconfirmed" for the dispatcher to ask (M3) or asked by the app (L3) — X3 decides.
4. Out of coverage → "something else: interpreter needed" (M4).
5. Phone sends codes in a locked envelope through a blind relay; console builds Japanese from its own
   checked phrasebook; tamper-evident log (M1 + L4).
6. Measured by readable tests (L5) and drills (M6).
Open: P10 (runtime work), P4 (M5, with Whisper).

## 7. Experiments, cheapest first (pass lines written before each runs)

| # | Question | How | Cost |
|---|---|---|---|
| X1 | Can blocks make correct Japanese? | ~50 sentences from candidate blocks; founder checks finished sentences; count meaning errors vs merely unnatural | 1–2 h, no code |
| X3 | Who should ask: app or dispatcher? | Paper prototype; founder as panicking caller, ~10 scenes; time + wrong taps, both ways | an afternoon |
| X2 | Does a bigger phrasebook hurt accuracy? | Blocks for 2–3 body areas; AI locked to blocks (with exits) vs not; small new founder-written pool | a few days |
| X4 | What promise can we afford? | Labelled pool: error limit vs amount sent, with/without back-off | after data |
| X5 | Can security lock the dispatcher out? | Break things on purpose: wrong key, server down, repeated message | with relay build |
| X6 | Does the app make the dispatcher faster? | Drills with real people | later |

## 8. Coverage check (2026-10-14, founder asked: do these ideas cover every issue?)

Covered by the ideas: P1–P3, P5, P7, P8, P9 (as a tradeoff to manage), P12. Partly: P4 (M5, waits for
Whisper), P6 (only drills/pilot can prove trust). NOT covered by any idea — stated plainly:
- Speech front end (accent, panic, noise; Whisper on hold) — errors there flow into everything after it.
- Phones (checker size, real-phone speed) — separate runtime work.
- Data (founder is the only author) — limits what L2 can promise until drills.
- Registration uptake (Smart911 Arkansas: under 2% of households after ~3 years) — not technical.
- First fire department / FDMA conformance — not technical.
- Privacy law (who is the data controller) — L4/M1 reduce risk; the legal answer still needs checking.
Unknown unknowns: the gap study (#4c) is the tool for finding dispatcher needs we have not seen yet.
"Not just a medical translator": the design never translates. It turns speech into structured, checked
facts with a proven error limit, asks a human when unsure, and delivers codes the console renders from its
own verified phrasebook. Closest descriptions: a safety-critical structured reporting system, or
"verified-by-construction emergency communication".

## 9. Second pass (2026-10-14): adjusted ideas, feasibility

Competition notes: moved to COMPETITIONS.md (local only — this repo is public).
**Adjusted ideas:** L1 keeps the 28 as valid codes, mandatory exits, grows by measurement, CPDLC precedent
(ICAO Doc 4444 coded message set, free text discouraged, voice in parallel). L2: honest ranges first, two
calibrated lines → send / unsure / drop. L3+M3 merged into "uncertainty routing": AI-unsure-of-meaning →
at most one caller question, never blocking the call; caller-unsure-of-facts → "unconfirmed" to the
dispatcher with a one-tap ask; flags rare and dispatch-relevant (drug-alert override 49–96%, van der Sijs
2006). M1: one shared phrasebook package and renderer, codes never reused (Protocol Buffers rule),
append-only versions, consoles update first, unknown code → "confirm by voice" (CPDLC ERROR + voice
fallback). M2: human-built tree, "less specific, never less severe", marked "details unconfirmed", never for
critical items. M4: reduced to "never silently drop" — no interpreter instruction; dispatchers already use
three-way interpretation (FDMA: 673/720 HQs = 93.5% on 1 Jan 2025; 6,248 uses in 2024). M5: feasible in
principle, needs multilingual training (see EXPERIMENT_LOG 2026-10-14). Privacy: blind relay matches PPC
Q&A 7-53 ("cloud exception": provider contractually and technically does not handle the personal data) —
Q&A, not statute; legal check still needed.

## 10. Third pass (2026-10-16): dual deployment, minimal UI, M2 depth, deployment-first

Competition notes: moved to COMPETITIONS.md (local only — this repo is public).
**Dual deployment (founder's concern = operating two live sides alone).** The console exists in FDMA's
route regardless of M1 (専用端末 installed by the service). Keep it to "phone app + one server": console =
web page served by the relay server; codes permanent and append-only so phone and server never need
synchronized releases; no console work until a department joins. Real burden = FDMA operating conditions
(fixed IPs, ≥1-year logs, intrusion detection) — exists with or without M1. Trade-off: a server-served web
console weakens "server can't read" → installed console app may be needed for full operation.
**Minimal UI.** Caller: one card, one "Call 119" button (always), tap-to-remove a wrong line, at most one
skippable question. Dispatcher: one card, at most two grey "unconfirmed" lines, one "Ask" button each.
**M2 depth.** Every field backs off (body part → region → injury; side → side unclear; time → time
unclear; symptom → protocol category). Middle level = the 21 症候 of FDMA 緊急度判定プロトコル Ver.3 (119番
通報); top = its own catch-all 「具合が悪い・気分が悪い」. Precedent: ICD-10 "unspecified" codes.
**M4.** No separate effort: only a console line when the AI uses L1's "something else" exit, if reliable.
**Deployment-first scope (founder, 2026-10-16: solo, no deployment experience, cannot abandon).** Phase 1 =
end-to-end real version (phone app, server + web console, codes, minimal phrasebook extension, minimal
uncertainty routing, honest error ranges, bounded speech-robustness work, basic security). Phase 2 = after
first users (full proven limit — needs real-caller data anyway —, back-off tree, full blocks, crypto
hardening, multilingual checker). Tier 0 (profile on dial) needs no AI and can ship first.
**Speech (founder: must clearly beat generic apps on accented/panicked speech).** Bounded plan when Whisper
returns: accent + noise test (L2-ARCTIC on disk), baseline, vocabulary prompt, LoRA only if a measured gap
remains (MAS-LoRA, Interspeech 2025, fine-tuned Whisper on L2-ARCTIC), judged by symptoms reaching the
card, pre-registered margin over default Whisper.

## 11. Fourth pass (2026-10-16): deployment pathways, speech advantage

Founder context: solo, no deployment experience, cannot afford to abandon → deployment risks must be found
early. (Personal timeline details are kept out of this repo — it is public on GitHub.)
**Deployment facts (researched).**
- App stores: Google Play Console requires 18+ (government ID, card); Apple paid enrollment effectively
  18+ / age of majority. Apple guideline 5.1.1(ix): apps in highly regulated fields such as healthcare,
  or that require sensitive user information, "should be submitted by a legal entity ... and not by an
  individual developer". 1.4.1: medical apps get greater scrutiny. 5.1.3(ii): no personal health
  information in iCloud (design rule: exclude the profile from iCloud backup). 5.1.3(iii–iv): health
  research in apps needs consent and ethics-board approval. Google Play: Health apps declaration;
  non-device health apps must state they are not medical devices. Japan: medical-device status is decided
  by intended use (MHLW guideline, last revised 2023-03-31) → no diagnosis or urgency scoring.
- Large models: App Store package limit 4 GB; downloads after install allowed → ship small, fetch models
  on Wi-Fi.
- Problem evidence: cities tell foreign callers "say the address first" because interpreter connection
  takes time (Fukuoka, Kobe, Otaru); no national measurement of foreign-language 119 call timing found →
  drills would produce new evidence.
- Fire-department route: Live119 still expanding (Hiroshima 2025, Nagasaki FY2026); TFD INNOVATION
  PROJECT is theme-based and company-oriented (themes 2026: EV fires, sea rescue, digital-human training,
  drones, ambulance heat) — watch, not a route today.
**Pathways, by feasibility:** drills (no institution) → pilot via TestFlight / Android closed testing
(adult or organisation account) → distribution partners for users → store release with a legal-entity
publisher → fire-department integration via a partner (Dawn Corp) or a university lab.
**Speech advantage ("knows who is speaking and what to listen for").** Profile-conditioned (language,
accent adapter — MAS-LoRA: known accent improves further; personal vocabulary from the profile);
task-aware keyword biasing (Sun et al., Interspeech 2023, Whisper + TCPGen; trie-based hotword decoding
needs no retraining); several candidate transcripts + LLM correction (HyPoradise, NeurIPS 2023);
hallucination guard (Careless Whisper, FAccT 2024: ~1% hallucinated phrases, more with pauses and
disfluency); wideband on-phone recording before the call (dispatch-centre ASR works on 8 kHz phone
audio). Evidence the problem is real: Whisper Turbo 52.9% → 63.5% WER on stressed/dialectal Albanian
crisis speech (2025). L2-ARCTIC (CC BY-NC 4.0) covers Mandarin, Vietnamese, Korean accents (Japan's
three largest foreign-resident groups) but is non-commercial → Common Voice (CC0) for a product.
On-phone: whisper.cpp supports prompts and beam search; n-best output is not exposed → engineering.

## 12. Fifth pass (2026-10-16): gateways, drills, "is it research?", speech realism

**"Is our work research?"** Honest: it is engineering + evaluation (applied information science), not basic
science. IPSJ junior winners are mostly built systems with an evaluation; ISEF has engineering categories but
rejects demonstrations without original research/design. For research contests, lead with the measured
experiments (checker study now; the drill study later). Full catalogue: COMPETITIONS.md.
**Founder pushbacks checked.** Apple's official enrollment page: individuals must be "the legal age of majority
in your region" (18 in Japan); Google Play: 18+. Founder turns 18 during 2027, so this resolves itself; before
then a parent's account covers testing. Apple 5.1.1(ix) (healthcare / sensitive data → legal entity) still
applies regardless of age. Dawn Corp: TSE Standard (2303), GIS company; NET119 >70% and Live119 ~50% of the
population served by fire departments (May 2025); no multilingual feature found; no sign of seeking partners →
not part of the plan (founder agreed it looks infeasible).
**Gateways (the "school principal" equivalent), researched.** (1) The founder's own school community, if it has
families who don't speak Japanese (to ask). (2) 119/disaster training for foreigners that fire departments
already run: Iwaki (June 2025: mock 119 call in a Japanese class, using three-way interpretation), Numazu
(2024), Kikuchi (technical intern trainees practising 119 calls on phones); Tokyo's 外国人支援防災訓練 with
registered disaster-language volunteers and a fire station taking part. (3) Japanese classes and language
schools. (4) Organisations obliged to give 特定技能 life orientation (8+ hours, including emergencies) —
explicit 119 practice not confirmed.
**Drill design, from published methods.** Meischke et al. 2015 (J Immigr Minor Health): randomized simulation
with 139 limited-English Spanish and Chinese speakers; interpreter connection added almost 2 minutes. Their
2013 study: language barriers increase time to dispatch and reduce accuracy of the level of aid. Dispatch
simulations use actors with scripted scenarios (Nashville trial; Vienna video-call study NCT06598592, endpoint
call duration); varied scripts to avoid learning effects; pre-specified start/stop points. Human-participant
studies need consent (parental for minors) and, for JSEC/ISEF, ethics approval before data collection.
**Speech realism.** Wispr Flow: $2B valuation (Aug 2026, $280M Series B); its own accent method compares
several transcriptions ("accent confidence scoring") — the same idea as our "several candidates". Extra size:
keyword biasing, candidates, personal words ≈ 0 MB; silence detector ~2 MB; an accent adapter a few MB. Only a
larger Whisper model adds hundreds of MB. Build as a separate, switchable speech layer, each part measured.

## 13. Corrections and Live119 (2026-10-20)

- Three-way interpretation use in 2024 (FDMA, Feb 2025): 6,248 uses = 3,427 ambulance, 49 rescue, 30 fire,
  2,742 inquiries etc. Trend 3,688 (2022) → 5,361 (2023) → 6,248 (2024). FDMA does not publish how many
  succeeded or how long connection took. Quote "3,427 emergency calls", not "6,248".
- Tokyo FD: five guaranteed languages; others "as far as the interpreting company can" (best effort).
- Live119 takeaways: zero friction (SMS link, no app); video is language-independent; it needs a Japanese
  conversation first (to explain the SMS and speakerphone) — the step a non-Japanese caller struggles with.
  Video and our system are complementary (video: what is visible now; ours: address/room, history, what the
  caller says, available before a shared language exists). Tiers exist for reliability (tier 0 never waits
  for the AI), not to sell parts.

## 14. Sixth pass (2026-10-25): early NET119, iPhone background limit, uncertainty-routing spec

- **Early NET119 (the right comparison).** Before 2017 each fire HQ built its own text-119 system (e.g. Kyoto's
  Web119); only ~20% of HQs had one in April 2016, with no interoperability. Turning points: FDMA study group
  (2015–16) → standard specification (March 2017) → national disability plan target "all HQs by FY2020" (March
  2018) + local allocation tax funding (FY2018) → 659/720 HQs (April 2025). Lesson: niche emergency services
  scale through a standard + a policy target + funding, not features. We already have the standard door (2024
  standard interface); our need is partial (interpreters exist) and our policy push is weaker.
- **iPhone background limit (found while reviewing external advice).** iOS blocks GPU (Metal) work once an app is in
  the background; a whisper.cpp report shows an app crash on iOS 26.2 when backgrounded mid-transcription;
  background grace is ~30 s (beginBackgroundTask). Consequence: the AI must finish in the FOREGROUND, before the
  dialer opens (or fall back to CPU). Speak → process (foreground) → card + Call. Measure on a real phone.
- **Uncertainty routing, specified.** App question: only when two mutually exclusive, dispatch-relevant items are
  both in the calibrated "unsure" zone (KnowNo rule: ask when the calibrated set has >1 option) and the caller
  did not say they were unsure; max one question, built from verified blocks, ≤3 options + "neither", never
  blocks "Call 119", auto-dismisses. Dispatcher line: only for the caller's own uncertainty (or a skipped
  question) on a dispatch-relevant item; phrased as what the caller said ("chest or abdominal pain — caller
  unsure"), never as an AI disclaimer; max one line; no action required. Breathing/consciousness: buttons only.
- **Founder decisions 2026-10-25:** build everything buildable now, discuss real-data mechanisms later; other
  languages not immediate (but drill languages must work through the speech path).

## 15. Seventh pass (2026-10-27): small-data critique, "possible" tag, deep learning, speech UVP

- **Critique "287 sentences is micro".** Partly outdated ("tumbled down the steps" is caught since the llama.cpp
  switch), but valid in substance. Weaknesses list: small locked sets (34/41/52 → wide uncertainty), all text
  written by us (not real speech), English-only checker, no real-audio tests, single utterance only, Stage A
  still prompted, hypothesis wording sensitivity, seed stability unknown, no phone measurements.
  Plan: thousands of generated paraphrases for TRAINING only (incl. idioms, hedges, negation, counterfactual
  pairs), founder spot-checks a sample; tests stay human-reviewed and locked; idiom/contrast suites in L5.
- **Founder's "probable symptom" tag (adopted in improved form).** Per-symptom certainty field (the CERTAINTY axis
  from the 2026-08-12 modifier design): two hypotheses per symptom — definite ("is having a seizure") and
  possible ("may be having a seizure"). Definite entailed → plain; only possible entailed → tagged "possible"
  (caller card and console); neither → dropped. Possible critical items are still sent (tagged), never dropped.
  Replaces the separate "caller unsure" line.
- **Deep learning.** Conformal calibration is statistics wrapped around neural networks; all our models are
  neural networks. Real deep-learning additions: checker trained on far more data, Whisper accent/noise LoRA,
  Stage A recall LoRA, learned score fusion before calibration.
- **Speech UVP (later phase, founder's idea).** Honest view: strong and defensible if built on a custom test set of
  accented, stressed, noisy emergency speech + measured adaptation gains. Not before the MVP.
- **Co-founder:** not needed to build; revisit at drills/pilot (an adult partner for accounts/contracts,
  Japanese-language relationships with fire departments, drill operations; ideally medical/emergency background).
