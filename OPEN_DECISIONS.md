# Open decisions & known gaps

Running list so nothing gets silently forgotten. Not a task list — these are things
that need a judgement call, not just implementation.

## GUIDING SLOGAN

**We do not try to beat the human interpreter — at every step we reduce the GAP.**
Respect what only a human can do; contest only where we can honestly close distance.
Our advantage over the interpreter is PREPARATION (pre-stored profile delivered instantly),
NOT out-comprehending panicked speech. Keep the two latencies separate: time-to-critical-info
(design advantage) vs inference latency (Intel/OpenVINO engineering showcase).

## WHAT THIS PROJECT IS (written 2026-08-12, after the base felt like it was drifting)

Three claims. Everything else is implementation and can change without touching these.

1. In the opening ~60 seconds of a 119 call, the bottleneck is NOT translation quality - it is
   that a panicking non-Japanese speaker cannot produce structured, dispatcher-usable
   information at all.
2. Our advantage is PREPARATION (pre-stored verified profile, pre-verified Japanese terms),
   not out-comprehending panicked speech.
3. Every Japanese string reaching the dispatcher was verified by a human IN ADVANCE.
   Nothing is generated live.

**The ontology is not the thesis - it is the MECHANISM that delivers claim 3.** A fixed list of
pre-verified terms is how we guarantee no unverified Japanese ever reaches a live emergency
call. That is its entire job.

### Ontology size: what actually constrains it (CORRECTION)

Earlier framing treated "more entries = worse latency" as a project law. It is not - it is an
artefact of how Stage A is built (all entries pasted into the prompt, re-read every call, see
`_build_messages` in slm_classify.py). Swap Stage A for embedding retrieval and that coupling
disappears; entries become nearly free.

The REAL constraints on ontology size, which do not go away:
- **Verification effort** (founder time). 13 of 29 are still `verified: false`. At 200 entries
  this is the binding constraint, and it is human hours, not compute.
- **Precision.** More near-identical neighbours (背中が痛い vs 腰が痛い) = more room to pick a
  plausible wrong one. Coverage up, accuracy risk up.

So: bounded by verification effort and precision. NOT by latency. And "more is better" is also
wrong - it was never a target in either direction.

### Positioning vs 救急ボイストラ (do not lose this again)

- Their 46 定型文 are FIXED PHRASES (46 sayable things). Our 29 are COMPOSABLE entries that
  combine with frame + profile + critical fields + location state. Counting one against the
  other is a category error.
- They are CREW-SIDE (paramedics, on scene, after arrival), at 96% national adoption - that
  fight is over, do not pick it.
- We are CALLER-SIDE, DURING the call, BEFORE dispatch. Different moment, different actor.
- What they structurally CANNOT have: the prepared profile (age, conditions, address). They can
  only translate what a panicking person says in the moment.
- Claim "the opening 60 seconds", NOT "10x better than existing solutions". A precise claim we
  can demonstrate beats a multiplier we cannot.

## THE REAL-WORLD USE CASE - defined 2026-08-12 (was never written down)

This existed only as an unstated assumption for weeks. Every design decision already implied it;
nobody had said it out loud, and it kept causing confusion.

**Target scenario:** a household with a KNOWN AT-RISK PERSON (elderly relative, heart condition).
A family member with limited Japanese is present when they collapse. At home.

**Physical setup - TWO DEVICES:**
- Phone: dials 119, on SPEAKERPHONE.
- Home device (laptop/tablet): runs this app, ALREADY OPEN, model already warm.
- Audio path is acoustic: device speaker -> phone mic -> dispatcher.

Two devices is NOT a Streamlit limitation. A phone cannot inject app audio into a live call -
call audio and media audio are separate streams, and echo cancellation would actively suppress
it. Even a native phone app would end up doing speakerphone + acoustic pickup.

The app MUST already be running. Waking a laptop, opening a browser and loading a 3B model takes
minutes. `warm_brain()` was written to load at app-open rather than mid-emergency - that function
only makes sense under this assumption, so the code had already answered this question.

**DIAL 119 FIRST. Always.** Never delay an emergency call to prepare a better message.
Dispatchers routinely handle panicking, silent or incoherent callers; 30 seconds of fumbling is
normal to them. Never getting usable information is not.

**Honest scope limit, state it in the pitch:** this does not help someone alone, away from home,
or without the device set up. It is a HOME emergency tool for a household with a known at-risk
person. Narrower than "helps foreigners call 119" - and far stronger, because every design
decision already fits it (stored address, stored patient profile, stored conditions, warm model).

## Location goes FIRST - flow restructured 2026-08-12

**The bug, found by walking through a real scenario minute by minute:** `ask_location` was step 7
of 9. The dispatcher answers with 「火事ですか、救急ですか?」 at ~0:08, and heard SILENCE until
~1:00 while the caller recorded, transcribed, classified and confirmed - before finally playing a
chunk whose first word (救急です) answered the original question. We made them wait a minute for
a word we had before the call started.

**Fix:** new `dispatch_now` phase immediately after the EMERGENCY button. 救急です + the address
need NOTHING from the pipeline - one is a constant, the other is in profile.json. Plays at ~0:13.
The briefing phase then starts at chunk 1, since chunk 0 was already delivered ("Back" can still
reach it if the dispatcher asks for the address again).

**Why this is correct, not just faster:** dispatch happens on LOCATION + TYPE, not on diagnosis.
The ambulance rolls and the crew is updated by radio en route. Travel time (~10 min nationally,
worth re-verifying) dwarfs everything, so gathering symptoms before dispatching just adds delay
to every case. Matches our own NET119 finding exactly: 救急/火事 + location connects immediately,
details follow. NET119 is CALLER-side, confirming the pattern is already accepted in Japan.

**Consequence: inference latency is now a POLISH problem, not a safety one.** The ambulance is
moving before the SLM has finished thinking. This is the strongest answer to "isn't 6-9s too slow
for an emergency?" - and it reinforces the Stage-A decision below.

**Details still do real work** (they arrive minutes before the crew does): response upgrade
(PA連携 - a fire engine dispatched alongside for suspected arrest), crew pre-briefing, and
attacking the 3-6 minute on-scene delay the FDMA measured.

**Gap this exposed:** after dispatching, dispatchers do 口頭指導 - talking the caller through CPR
in Japanese. That is inbound, we are outbound-only, and it is genuinely life-saving. Belongs in
the honest-limitations section; a judge who knows this field will ask.

## Stage A stays an LLM - embedding retrieval REJECTED (2026-08-12)

Considered replacing Stage A (candidate generation) with embedding retrieval: ~70x smaller
model, milliseconds instead of ~6-9s, and it would have decoupled ontology size from latency.

**Rejected, and the reasoning matters more than the verdict:**
- Stage A + Stage B were designed together as ONE anti-fabrication system, with measured
  results behind it (90% exact, precision 1.00, zero fabrications, recall 0.89). Replacing half
  of it with something unmeasured trades a known good for an unknown.
- Embeddings compress a whole utterance into ONE vector, so filler and repetition DILUTE the
  signal ("oh god oh god he's— his chest" averages the noise in with "chest"). An LLM reasons
  through disfluency; similarity search cannot. Panicked speech is exactly our input.
- Latency is what OpenVINO/INT8 exists to solve. Solving it architecturally SHRINKS the Intel
  story instead of showcasing it - wrong trade for this project.

=> Latency is handled by Intel/OpenVINO optimization, not by changing the architecture.
=> The ontology stays at 29. Not a limitation to apologise for: "the opening 60 seconds"
   is the claim, and 29 well-chosen entries serve it.

**IMPORTANT GAP THIS SURFACED:** accent IS tested (L2-ARCTIC), but PANIC/DISFLUENCY has never
been tested at any stage. `slm_testset.json` is synthetic and clean - our own notes call it
"optimistic vs real panicked/accented Whisper output". Perturbed-transcript testing (injected
repetition, filler, false starts) is a real open gap regardless of which Stage A we use.

## Modifier system - DESIGNED, deliberately NOT built (2026-08-12)

The wording problems found during the ontology verification pass are not 6 separate issues.
They are 4 axes:
  ASPECT    ongoing vs finished        (vomiting, seizure, bleeding)
  SOURCE    caller saw vs patient said (difficulty_breathing, choking - `source_dependent`)
  CERTAINTY confirmed vs couldn't-tell (no_pulse)
  SEVERITY  weak vs cannot-move        (one_sided_weakness)

**`frame` IS ALREADY ONE OF THESE.** It is a modifier stored on the entry and applied at render
time by `_format_statement`. The pattern exists; only one axis of it was ever built.

The generalization: entries gain OPTIONAL named variants, e.g.
    "japanese_term": "けいれんしています",
    "forms": { "aspect_finished": "けいれんしていました" }
The renderer picks a variant when the modifier says so, else the default, then applies `frame`.
NOT grammatical conjugation in code (a project in itself) - hand-written variants, opt-in per
term. Cost stays ~linear (29 terms + ~6 variants), not the 116 a full cross-product would need.

**Why NOT built now:** only 2 terms are affected today (vomiting, seizure). A modifier system to
fix 2 terms is scope creep. Safe defaults used instead - ASSUME ONGOING, because saying
けいれんしています when it stopped merely over-prepares the crew, while the reverse under-prepares
them. EMS practice errs toward over-triage.

**SHARPENED 2026-08-12 - the aspect problem is NOT universal, it is 4 terms.** Categorising all
29 by how they behave in time:
- **19 are STATES** (pain, fever, pallor, consciousness). A state describes NOW; there is no
  aspect to resolve. Stored です/ます.
- **3 are DISCRETE EVENTS** (倒れました, 頭を打ちました, 溺れました) - already stored past,
  completed by definition. Correct as-is.
- **7 use ています**, but only 4 describe something that can genuinely STOP while still being
  worth reporting: `vomiting`, `seizure`, `heavy_bleeding`, `choking` (object dislodges ->
  のどに何か詰まっていました). 冷や汗 and 体が冷たい do not reverse; 息をしていません comes from
  the deterministic question, not the model.

So the ontology ALREADY handles this for 25 of 29 by choosing the right form per term TYPE.
That was a good implicit design choice - states get です/ます, discrete events get ました.

**And the strongest argument is for doing nothing at all:** a safe default cannot be wrong in
the DANGEROUS direction. A model-detected aspect could report "finished" while a seizure is
ongoing, under-preparing the crew. Trading a guaranteed-safe default for a model guess that can
fail unsafely is a DOWNGRADE for these 4 terms.

**Revised trigger (the earlier "mandatory before expansion" framing was wrong):** the general
modifier system is genuinely OPTIONAL, not deferred-mandatory. Expansion is off the table anyway
(see the embedding decision above).

### RESOLVED for those 4 terms - built 2026-08-12, via the human, not the model

The 4 aspect-ambiguous terms now carry a `forms.finished` variant in ontology.json, and the
confirm-symptoms screen shows a "Happening now / Has stopped" choice for any entry that has one.
Data-driven off `forms`, so no hard-coded id list in app.py.

  vomiting        吐いています        -> 吐いていました       (founder-confirmed)
  seizure         けいれんしています   -> けいれんしていました   (mechanical, unchecked)
  heavy_bleeding  血がたくさん出ています -> 血がたくさん出ていました (mechanical, unchecked)
  choking         のどに何か詰まっています -> のどに何か詰まっていました (mechanical, unchecked)

**Why the human and not the SLM:** a model-detected aspect can fail in the DANGEROUS direction -
reporting "stopped" during a live seizure under-prepares the crew. A human answering a direct
question cannot. Same principle as the awake/breathing/circulation buttons: when the answer
matters and we cannot know it, ASK - do not infer. Costs one extra tap, and only when one of
these 4 actually fires.

This is the general modifier design applied narrowly to the cases that need it. If it ever needs
generalizing, the shape is already there (`forms` on the entry, resolved at render time).

STILL NEEDED: founder check on the three "mechanical" variants above.

## Ontology wording - open questions, recorded not fixed (2026-08-12)

Flagged during the verification pass; judged non-blocking, need a Japanese-language call:
- `slurred_speech` 呂律が回りにくいです - the set idiom is 呂律が回らない. Is 回りにくい a
  deliberate softening or should it be 呂律が回っていません?
- `one_sided_weakness` 体の片側が動きません - triggers include "one side is weak", but 動きません
  means cannot move AT ALL. We may be upgrading weakness into paralysis.
- `face_drooping` 顔がゆがんでいます - ゆがむ reads closer to "distorted/twisted" than "drooping".
  The protocol does use 顔のゆがみ, so probably fine.
- `difficulty_breathing` 息が苦しいです is `source_dependent` and currently renders as a direct
  assertion, i.e. it states the patient's internal sensation as observed fact. Resolving this is
  the `source_dependent` work already deferred to the SLM.

## Gap-reduction levers (reduce distance to the human interpreter)

Fold the cheap wins into Week 2 alongside the OpenVINO work. All discussed 2026-07-27.

- **Force the caller's known language** (from `profile.json` native_language, currently UNUSED)
  instead of Whisper auto-detect. Kills a whole failure class on short/accented speech. Cheap.
- **Anti-hallucination Whisper settings** (`condition_on_previous_text=False`, no-speech /
  logprob thresholds). Directly targets the repetition-loop hallucination we observed. Cheap.
- **Low-confidence re-ask** — if STT confidence is low, ask the caller to repeat rather than
  guess. Mimics the human's single most valuable behavior (clarifying). Founder "really liked
  this idea — definite, but for later." Medium effort (needs confidence scores out of Whisper).
- **Bigger Whisper model** (base -> small/medium): biggest raw accent-accuracy gain; cost is
  latency, which Intel/INT8 buys back. Real robustness-vs-speed tradeoff to tune, not hide.
- **VAD (trim silence/sobbing before STT):** reduces hallucination on disfluent panic. Medium.
- **Context/idioms/common-sense:** that's the SLM's job (Week 2), already planned.
- Honest bound: these NARROW the gap, they don't erase it. Safety net = confirmation loop means
  our failures are caught, not catastrophic — a legitimate answer to "worse at comprehension".

## Blocking correctness

- **Patient identity — RESOLVED (built in A.3).** `app.py` has an `ask_patient` confirmation
  step; if not confirmed, patient details (age/sex/conditions) are omitted from the briefing
  rather than stated wrong. `pipeline.py`'s `confirm_patient` does the same for the CLI.
- **Unverified Japanese flows into briefings silently.** STATUS 2026-08-03: the original 16
  terms ARE founder-verified; the 13 added from the 緊急度判定プロトコル (12 + `nausea`) are
  `verified: false` and awaiting check. Nothing in the code enforces the flag - an unverified
  term still reaches a briefing without warning.

## Must be handled — semantics, context, completeness

Raised by the founder. These are things a human interpreter does that the system currently
does not. Not hypothetical; each has a concrete failure case.

- **Completeness is never checked.** The confirmation loop asks "did we hear you right?",
  never "did you tell us enough?". "Please help, my father, please come" transcribes
  perfectly, confirms happily, and produces a briefing with no symptoms and no breathing
  status. Accurate and useless.
  **Fix:** if the critical fields (breathing, consciousness) are absent from the transcript,
  prompt for them — "Is he breathing?" / "Is he awake?" — in the caller's language.
  Highest-value correctness work currently outstanding.
- **Contradictions pass straight through.** A transcript containing both "he's talking" and
  "he's unresponsive" emits 意識がある and 意識がない side by side, unflagged.
- **Vague or context-dependent statements are lost.** "He's not doing well", "he took his
  pills this morning" — a human interpreter probes; the ontology cannot. Partly mitigated by
  the caller's-own-words fallback slot, which at least preserves the raw statement.
- **Not fixable, and should be stated plainly in the pitch:** the system can only ask
  questions it anticipated. Open-ended clarification is the dispatcher's job, which is why
  the honest claim is "the opening 60 seconds", not "the conversation".
- **Frame / source of information (deferred to the Week-2 SLM).** Whether a symptom came
  from the patient's mouth or the caller's eyes is clinically meaningful - "he says he can't
  breathe" (conscious) vs "he isn't breathing" (arrest) are opposite severities. Terms are
  tagged in ontology.json as observed / reported / source_dependent. The source_dependent
  ones (difficulty_breathing, choking) can only be resolved by reading the caller's actual
  sentence, which the crude Week-1 matcher cannot do - the SLM must. A good SLM should also
  de-duplicate ("can't breathe" said twice = one symptom) and strip panic filler ("oh my
  god"). This is the core reason for SLM+ontology over literal translation.
- **The confirmation loop checks the transcript, not the frame.** It shows the caller the
  English it heard, so it catches mis-transcription but NOT a wrong frame in the Japanese.
  Catching that may need showing a back-translation of the generated Japanese. Open; harder.
- **"Breathing addressed" is treated as binary by the critical-fields prompt.** If the caller
  mentions difficulty_breathing OR not_breathing, the tool won't then ask "is he breathing?".
  But "having trouble breathing" and "is he breathing at all" are different clinical questions -
  a patient can have laboured breathing now and stop moments later. Reasonable Week-1
  simplification; revisit when the SLM can reason about breathing state more finely.
- **Sentiment is fine and needs no work** — the caller is on the phone, so the dispatcher
  hears panic directly in the human voice. A payoff of keeping a human in the loop.

## Needs a Japanese speaker

- All 16 `japanese_term` values in `data/ontology.json` — verify against real 119 intake usage.
- The label `通報者の説明：` in `src/briefing_template.py` — does it read naturally to a
  dispatcher? Alternatives: 通報者によると / 通報者の話では / 補足.
- The fallback `詳細不明` when nothing matches — right thing to say, or better to omit the
  section entirely rather than announce an empty field?
- Specific term questions are recorded in the `note` fields inside `ontology.json`.

## Considered and deprioritized

- **Onomatopoeia (ズキズキ, ゼーゼー, ぐったり).** Conveys pain-quality nuance, which is already
  filed as "acceptable to degrade". Judged an overstep relative to the core mission (getting the
  main critical points across). Not pursuing.

## SLM classification — decided (2026-07-29)

- **Model: Qwen2.5-3B-Instruct** (not 1.5B). 1.5B was unreliable (inverted critical fields).
  3B chosen for accuracy; INT8/OpenVINO to recover latency later.
- **Architecture: two-stage + architectural split.**
  - Critical BINARY statuses (conscious/unconscious/not_breathing) are NOT classified by the
    SLM (`SLM_EXCLUDE`) — they come from deterministic `ask_critical_fields`. Removes the
    dangerous inverted-consciousness error class.
  - Stage A: candidate generation (high recall, few-shot, fuzzy-parse of ids so "chocking"->
    "choking").
  - Stage B: per-candidate yes/no VERIFICATION pass with clean one-line descriptions,
    keep-biased. This is the anti-fabrication mechanism.
- **Measured on a 40-case synthetic test set** (`benchmark/slm_testset.json`,
  `benchmark/eval_slm.py`): final = 90% exact, precision 1.00 (0 fabrications), recall 0.89,
  F1 0.94. All remaining misses are under-reporting (safe direction).
- **Caveats:** verification adds per-candidate latency; synthetic test set is optimistic vs
  real panicked/accented Whisper output; recall 0.89 not perfect.
- **Still needed:** interpretation-confirmation (human sees understood symptoms, can remove a
  stray one AND add a missed one) — the final safety net on top of the SLM. Then wire SLM into
  pipeline behind a flag. Files: `src/slm_classify.py`.

## Language support

- The whole pipeline is **English-only by default**, never a deliberate decision.
  `trigger_phrases_en` is English; `profile.json` has a `native_language` field nothing reads.
- Whisper is already multilingual, and the Japanese output is language-neutral — so the
  architecture is fine. The English lock-in is in the crude Week-1 matcher, which the SLM replaces.
- Honest caveat for the pitch: Whisper accuracy varies a lot by language, and is weakest for
  some languages whose speakers are most vulnerable (Nepali, Burmese). Do not claim uniform coverage.
- Plan: English-first for the demo, verify one non-English language end-to-end (blueprint
  suggests Vietnamese; Chinese would perform better).

## Not-at-home line leaks app-internal jargon - RESOLVED 2026-08-04

- Was 「今いる場所は登録した住所と違います」("different from the registered address") - leaked
  our internal concept. Now: 「今、自宅にいません。」- plain, natural, no jargon. Still marked
  TODO(founder) in the code for a final naturalness check, but no longer blocking.
  File: src/briefing_template.py, TEMPLATE_LOCATION_UNKNOWN.

## Multi-person profile (raised 2026-07-30 by founder)

- profile.json holds ONE person. A call may be about someone else ("my dad" vs a saved
  72-y-o female). Current behavior is SAFE: confirm "is it \[saved person\]?"; if no, omit patient
  details (dispatcher asks). Fuller version = store multiple household members, pick who it is in
  the emergency. Real-product improvement; keep the safe one-person version for the PoC, build
  multi-person only if time allows.

## Briefing delivery pacing (raised 2026-07-30 by founder)

- The briefing is currently ONE long run-on sentence. A real 119 dispatcher takes notes at
  conversational pace and drives a back-and-forth (asks location, then symptoms, etc.), so a
  single blast would outrun them. Fine for the proof-of-concept (proves the content), but real
  use needs the briefing broken into PACED CHUNKS - lead with location + chief complaint (get
  the ambulance moving), then deliver the rest as the dispatcher asks. This is a Week-3
  interaction-design job (how the briefing is presented/delivered on the button screen), not a
  change to the Japanese itself.

## UI polish pass - RESOLVED 2026-08-04

- Mic-permission link hidden via CSS (`[data-testid="stAudioInput"] a {display: none}`).
- EMERGENCY button centering fixed (was a flex-container width bug, not just cosmetic) and
  resized per founder preference (400x230, 2.3rem).
- Secondary buttons (Start over, Yes/No, etc.) scoped to stay small/subdued; only
  `.st-key-emergency` gets the big styling.

## TTS — built, with a portability caveat (2026-08-03)

- TTS is NOT optional: the caller does not read Japanese, so on-screen Japanese is text they
  cannot pronounce. The app must SAY it. Core delivery path, not decoration.
- `src/speak.py` = pluggable offline backends: macOS `say -v Kyoko` (dev machine, working),
  then pyttsx3 (wraps the OS engine - SAPI5 on Windows) for the Intel/Windows demo machine.
- **OPEN RISK:** pyttsx3 on Windows needs a Japanese voice installed in the OS (language pack).
  UNTESTED on the Intel machine. If it fails there, fall back to a real offline model
  (MeloTTS supports Japanese; Piper's Japanese is weak - espeak phonemization).
- No autoplay by design: the caller CHOOSES to play each chunk (non-negotiable - an aid,
  never an automated broadcast into the 119 line).

## Inbound translation = TRIAGE, not blind translation (founder's design, 2026-08-03)

- Do NOT build a constant STT->translate->TTS pipe from the dispatcher to the caller. Instead
  the AI INTERPRETS what the dispatcher wants and only involves the caller when it matters:
  - dispatcher confirming something the caller already answered in the UI -> no need to interrupt
  - dispatcher asking something answerable from the profile -> answer without burdening the caller
  - dispatcher asking something genuinely new -> surface it to the caller
- Founder's caveat: the caller's follow-up "may or may not" be important - so this is a
  judgement, not a rigid rule. Avoid rigidity.
- Fits our existing architecture: same "classify into a known set" pattern the brain already
  uses, rather than free translation.

## 緊急度判定プロトコル Ver.1「119番通報」 - the OFFICIAL dispatcher protocol (2026-08-03)

Source: https://www.fdma.go.jp/singi_kento/kento/items/kento121_05_119banprotocolv1.pdf (70pp)
This is what 119 dispatchers actually follow. Directly comparable to our ontology.

**Their algorithm (question ORDER):** 119通報 → 年齢・性別・住所・通報概要(症候) → CPA疑い判定
→ 共通項目インタビュー(呼吸・循環・意識) → 症候別インタビュー. Target: dispatch order within
2 minutes of pickup (3 phases x 1 min: 予告指令 / 安全確保+CPA認識+出動指令 / 応急手当).
=> VALIDATES our design: identity+address+chief complaint first, then vitals, then detail.

**Their 3 vital-sign questions, VERBATIM (use these):**
- 呼吸: 「呼吸は楽にしていますか？」「いつもどおりの呼吸ですか？」
- 循環: 「冷や汗をかいていますか？」「顔色は悪いですか？」
- 意識: 「普通に話が出来ますか？」

**CPA keywords → immediate R1 (highest urgency):** 呼吸なし・脈なし・水没・冷たくなっている・
首をつった・首を絞めた・喉が詰まった. (We cover only not_breathing + choking.)

**Their 症候 list:** 呼吸困難, 動悸, 意識障害/失神, けいれん, 頭痛, 胸痛(非外傷性), 背部痛,
発熱(成人/小児), 腹痛, 嘔気・嘔吐(成人/小児), めまい, しびれ, 腰部痛, 外傷, 固形物誤飲,
小児の頭頸部外傷.
**Flagged HIGH urgency:** 呼吸困難・動悸・意識障害・痙攣・頭痛・胸痛・背部痛・腰痛.

**GAPS in our ontology (high-urgency ones we LACK):** 頭痛 (headache), 動悸 (palpitations),
背部痛 (back pain), 腰痛 (lower back pain). Also missing: めまい, 嘔気・嘔吐, しびれ.
**We also lack CIRCULATION entirely** - they assess 冷や汗 (cold sweat) and 顔色 (complexion)
as one of the three vital signs. We only cover breathing + consciousness.
**=> Our eval test-set labels were WRONG:** I labelled "turning pale" and "dizzy" as expect-[]
(restraint tests). 顔色が悪い is an official vital-sign finding and めまい is a listed 症候.

**VALIDATED:** 息が苦しい is literally their FIRST listed colloquial phrase for 呼吸困難 -
founder's plain-register call was right. Breathing+consciousness as critical = 2 of their 3
vital signs. Their 通報内容 lists per symptom = exactly our trigger_phrases concept.

## NET119 flow (2026-08-03)

Minimum viable emergency report = **救急/火事 + location** → connects immediately → details
by text chat afterwards. Confirms: TYPE + LOCATION is what gets help moving; everything else
is follow-up. Pre-registration required (fields not published; ask a fire department).

## Citable evidence from the Fire Agency's own documents (2026-08-03)

Source: FDMA 救急ボイストラ briefing PDFs (令和8年1月 / 平成30年4月).

- **THE stat for the pitch:** foreign patients' 現場滞在時間 (on-scene time before departing for
  hospital) runs **3-6 minutes LONGER** than average, explicitly because communication takes
  time (Sapporo City Fire Bureau data). The agency ties this to 救命率の低下 - concern about
  reduced survival rates. An official quantification of what the language barrier costs.
- **THE argument for our ontology over Google Translate, from the agency itself:**
  「既存の多言語自動翻訳システムを導入する消防機関も出てきているが、救急用のフレーズや
  傷病者とのやり取りの面で使い勝手の良いものになっていない」 - i.e. GENERIC translation
  systems are NOT fit for emergency phrases / patient interaction. This is third-party backing
  for domain-specific structured output vs raw translation - the exact competitive objection.
- 救急ボイストラ = **46 定型文**, 15 languages. (Comparable scale to our 16 situations.)
  The 46 phrases are NOT extractable - they appear only as screenshots in the PDFs. To compare
  ontologies properly we'd need another source or the app itself.
- **Adoption: 38.3% (2018) -> 96.0% (691/720 fire departments, Jan 2026).** Crew-side is
  essentially solved nationally -> confirms our on-site play must be the PROFILE, not translation.
- 2018 usage: 1,187 uses; Chinese + English dominate; several languages actually used had
  NO 定型文 (定型文なし) - a coverage gap even in the national system.

## Forced language assumes the profile is right (raised 2026-08-03, NOT FIXED)

- `src/stt.py` now forces Whisper to the caller's `profile.caller.native_language` instead of
  auto-detecting. Removes the wrong-guess failure class AND is ~20% faster (measured warm;
  an earlier "10x" claim was a model-loading artefact, corrected).
- **THE HOLE:** it assumes the caller speaks the language in their profile. Reality breaks this:
  a Vietnamese resident more comfortable in English; a mixed-language household; code-switching
  under stress. Forcing the WRONG language corrupts the entire transcript - the exact failure we
  were trying to prevent, just triggered differently.
- **Needed:** a quick language switch on the recording screen, and/or fall back to auto-detect
  when decode confidence is low. Neither built.

## GPS location (planned - from NET119 precedent, 2026-08-03)

- Send GPS coordinates instead of asking "are you at your registered address?".
- Double win: more reliable on THE most critical field, AND removes a whole question/tap
  from a panicking person's flow.
- Precedent: NET119 (the fire agency's own caller-side app for hearing/speech disabilities)
  already does exactly this - pre-registration + 救急/火事 choice + GPS + text chat. Our
  pattern is already accepted by Japanese fire departments.
- Founder notes GPS also solves >50% of the 火事 (fire) case, since location dominates there.

## On-site handoff to the ambulance crew (LATER - after STT robustness)

- Idea: once the call is done, the app shows a simple list of confirmed symptoms + profile
  info that the caller can SHOW the arriving crew.
- IMPORTANT positioning: do NOT compete with 救急ボイストラ on translation - it's deployed
  nationwide to fire departments already; duplicating it is a weak position. Our unique value
  on-site is the PREPARED, VERIFIED PROFILE (age, conditions, medications, allergies in perfect
  Japanese) which VoiceTra structurally cannot have - it can only translate what the panicking
  family says in the moment.
- Founder wants to FIRST research what is actually discussed on-site before building. Ordered
  after STT robustness.

## Not built yet

- Live microphone recording — RESOLVED, built in A.2 (`st.audio_input` in app.py).
- Inbound direction (dispatcher's Japanese → caller's language). Blueprint says cut this first if behind.
- Name fields in `profile.json` — needed for predictable dispatcher questions like 「お名前は？」.

## Risks flagged

- **Python 3.9, no Homebrew.** Week 2 Intel tooling (`optimum-intel`) may want a newer Python.
  Worth checking early rather than discovering it mid-conversion.
- Scope creep is the biggest threat to shipping. Core demo = button → panicked voice →
  confirmation → correct structured Japanese, offline.
- **Latency is a live risk until measured.** Whisper + SLM + optional TTS stacked on CPU can
  exceed the <2s target. OpenVINO quantization is the lever (Week 2), but "OpenVINO will fix
  it" is a plan, not a proof - measure the real number in Week 2 and put it in the pitch. The
  <2s target is about MACHINE responsiveness; human confirmation-loop time is safety, separate,
  and must not be conflated with it.

## Settled

- Skip AAC/compressed audio decoding. Real product records live from the mic, so no file
  format is ever involved. `afconvert` covers file-based testing.
- Resampling is done in our own code (`prepare_audio`), not left to transformers' automatic
  path, which garbled 48 kHz input into repeated nonsense.
