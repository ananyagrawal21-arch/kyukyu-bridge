# Open decisions & known gaps

Running list so nothing gets silently forgotten. Not a task list — these are things
that need a judgement call, not just implementation.

## POSTAL CODE LOOKUP - the romaji problem, actually solved (2026-08-19)

**The bug this fixes:** the setup screen let a user type their address in ROMAJI - the natural
mistake, since our user is defined as someone who does not read Japanese. The address is spoken
aloud by a JAPANESE voice, so "Tokyo / Edogawa / 4 chome" produced literal noise. Measured on a
real profile. The address is the single most critical field; this was silent and structural, not
cosmetic.

**The fix:** `src/postal.py`. Enter a 7-digit postal code (on every bill, lease, residence card)
-> looked up against a free public API (zipcloud.ibsnet.co.jp) -> returns 東京都江戸川区西葛西 in
correct kanji. The user never types Japanese for prefecture/city/ward at all. Wired as "Step 1"
at the top of the setup screen, ahead of everything else.

**THE NETWORK BOUNDARY - this is the only code in the whole project that touches the internet.**
It runs ONLY when the user presses "Look up" on the setup screen, a calm one-time activity. The
result is written into profile.json and never fetched again. The EMERGENCY PATH remains fully
offline - postal.py is never imported by anything the app does during a call. Failure here is
non-fatal (falls back to manual entry).

A fully-offline version is possible by bundling Japan Post's own KEN_ALL dataset (~120k rows,
their official source) instead of calling an API. Their direct download blocks automated
fetches (returns an HTML 404 page, checked 2026-08-19), so that is a manual step for later - the
module's public interface (`lookup(code) -> {prefecture, city_ward} | None`) would not change.

Also added: `looks_romaji()`, catching any FIELD typed in Latin letters (not just the
postal-code ones) with a persistent warning on the home screen until fixed. Digits are excluded
deliberately - a Japanese voice reads "405" correctly, so a numbers-only room number must not
false-positive. Lives in `src/postal.py` (not app.py) so app.py and the headless
`tools/setup_profile.py` share ONE implementation - it was written into app.py only at first,
which broke setup_profile.py's import; moved once that surfaced, caught before it shipped.

## FALL vs COLLAPSED - split into two entries (2026-08-19)

**The bug, found by the founder testing the app:** saying "fell down the stairs" classified as
`collapsed` (倒れました). Clinically wrong: 倒れました tells a dispatcher this was an internal
MEDICAL event (cardiac, neurological, fainting); a fall down stairs is TRAUMA, where the crew
may need spinal precautions. `collapsed`'s own trigger list included "fell down" and "fell
over" - the entry never should have covered mechanical falls.

**Fix:** new entry `fall` -> 転倒しました (`verified: false`, NEEDS FOUNDER CHECK), narrowed
`collapsed`'s triggers to medical-only language (collapsed, went down, went limp, passed out
and fell). English "fell" genuinely covers both causes, so trigger-phrase keyword matching
cannot decide this alone - per the founder's call, Stage B's descriptions carry the distinction
by CAUSE ("collapsed BY THEMSELVES from a medical cause" vs "fell BECAUSE OF an accident"), and
the SLM reads the whole sentence rather than keying off one word. Genuinely ambiguous cases fall
to the human via the existing confirm-symptoms screen, same principle as the aspect choice.

**A bug caught before it shipped:** the few-shot example teaching the model restraint said "she
tripped and fell, and her arm is bleeding heavily" -> `["collapsed","heavy_bleeding"]`. That
would have taught the model the WRONG mapping on every single call - a trip is exactly a `fall`.
Corrected to `["fall","heavy_bleeding"]`, plus a second example contrasting an actual collapse.
Caught here, but is a reminder: an ontology change is not complete until every place that
teaches the model (few-shot, Stage B descriptions) is checked, not just the entry itself.

**SUPERSEDED 2026-08-20 - it is now a THREE-way split, see the section below.** The two-entry
version described here was an intermediate step and its Japanese was wrong twice over. Kept for
the reasoning trail; read the three-way section as the current state.

**Re-running the eval after this change surfaced a real methodology finding first:** two
apparent "regressions" (head_injury and drowning cases now also returning `fall`) were not
model failures at all - the test labels PREDATED the `fall` entry, so there was never a slot
for it in `expected`/`acceptable`. Both cases genuinely describe falls ("he slipped...", "fell
into the bath..."). Fixed the test set (`benchmark/slm_testset.json`) to mark `fall` acceptable
in both, rather than accept a headline number without checking whether the eval itself was the
thing that was stale.

**The TRUE cost, measured after that fix, over the full 52-case set:**

    exact-match  96% -> 94%  (-2pt)
    precision    1.00 -> 0.98  (1 fabrication introduced)
    recall       0.96 -> 0.96  (unchanged)
    F1           0.98 -> 0.97

All 3 remaining failures (1 fabrication, 2 misses) are the SAME pre-existing cases already known
from earlier testing (the "her stomach is killing her" vomiting fabrication, the "boiling hot"
missed fever, the "pale and sweating" missed pale_complexion) - NONE are new failure modes from
the fall/collapse split. The split itself is clean; the small numeric cost is genuinely the
price of asking the model to resolve an ambiguity English does not disambiguate on its own
("fell" covers both readings), not a defect in how it was built.

## FALL vs COLLAPSE - the THREE-way split, current state (2026-08-20)

Grounded in standard Japanese EMS/nursing vocabulary rather than invented phrasing. Japanese
already carves this up, and 転倒・転落 is used as a recognised paired term in patient-safety
contexts:

    collapsed  倒れました    no mechanism stated - "he just collapsed", "went limp"
    fall       転倒しました   fell OVER on level ground - tripped, slipped, a rug
    fall_down  転落しました   fell DOWN stairs or a slope (in contact with a surface)

**墜落 (free fall through air - ladder, roof, window) is deliberately NOT modelled.** It is a
real and distinct term, but rare in the domestic setting this app is scoped to, and a fourth
lookalike entry is precisely what caused the misclassification described below.

**TWO Japanese errors were made getting here, both caught by the founder, both worth remembering:**
1. Claimed 倒れました signals a MEDICAL cause. It does not - 倒れる is CAUSE-NEUTRAL, it only
   means "went down". It is the right default when no mechanism is given, and for no other
   reason.
2. Used 階段から落ちました ("fell from the stairs") as the generic from-height term while its
   trigger phrases also covered ladders and roofs - so a ladder fall would have told the
   dispatcher the patient fell down STAIRS. A plain description masquerading as a general term.
Both were avoidable by checking the standard vocabulary first, which is what finally resolved it.

**A REAL FAILURE MODE, measured and fixed:** "fell down the stairs and hit his head" originally
returned ONLY head_injury - the fall vanished. Isolating the stages showed why, and every
component was behaving correctly:

    Stage A (propose) -> ['fall', 'head_injury']     <- picked the WRONG sibling
    Stage B (review)  -> ['head_injury']             <- correctly rejected `fall`, which its
                                                       own description says is level-ground

Stage B was right to reject it. But because Stage A never proposed `fall_down`, the correct
label was never in the list to survive, and the information was lost silently.

Root cause was the few-shot examples: the model saw only "she tripped and fell + injury ->
[fall, injury]" and pattern-matched that SHAPE for a stairs fall. Fixed by adding a CONTRASTING
example with the same shape but a stairs mechanism, answered `fall_down`. The examples now teach
the DISTINCTION, not just the output format.

**Verified 4/4 after the fix**, including the founder's exact phrasing:
    "he fell from the stairs"                          -> fall_down
    "fell down the stairs and is bleeding"             -> fall_down + heavy_bleeding
    "she tripped on the rug and cannot get up"         -> fall
    "he suddenly collapsed and is not responding"      -> collapsed

STILL NEEDED: founder check on whether 転倒しました and 転落しました are natural in a PANICKING
CALLER's mouth, or read too clinically. Both are currently `verified: false`.
**RESOLVED 2026-08-20 - founder confirmed both read naturally. No longer blocking.**

**Full 52-case regression after the fall_down addition:**

    exact-match  94% -> 92%  (48/52)
    precision    0.98 -> 0.98  (unchanged, 1 fabrication)
    recall       0.96 -> 0.94  (1 new miss)
    F1           0.97 -> 0.96

3 of 4 failures are the SAME pre-existing cases (vomiting fabrication, boiling-hot fever miss,
pale/sweating miss). ONE new miss: "he collapsed and now he's convulsing on the floor" ->
missed `seizure` (kept `collapsed`).

**This new miss is NOT about fall/collapse at all - and that is the real finding.** The
situation menu is the FULL ontology on every single call, so adding `fall_down` changed the
exact prompt text for EVERY case, including ones with no fall in them. A seizure case that
previously classified correctly can flip purely from prompt-length/content shift, with zero
change to seizure-relevant code. This is the mechanism the embedding-retrieval rejection and
the "ontology size bounded by precision, not latency" note already predicted in the abstract -
here it is concretely, in a real regression. Each new entry has some non-zero chance of
perturbing UNRELATED classifications. Not a reason to stop growing the ontology, but a reason
to always re-run the FULL eval after any addition, not just targeted tests of the new entry -
exactly what this session did, and exactly why it caught this.

## HOUSEKEEPING - found during a full-repo audit (2026-08-19)

- `pyttsx3` is imported by `src/speak.py` (the Windows/SAPI5 build-time TTS fallback) but was
  MISSING from requirements.txt. A fresh Windows install would fail to build audio with no
  obvious reason why. Added, with a comment clarifying it is a BUILD-time dependency
  (tools/build_audio.py) - the shipped app itself only ever plays pre-rendered files.
- `_format_address` was imported into app.py but never called - dead code left over from before
  the address-split refactor (render_location_pieces replaced it). Removed.
- `pipeline.py`'s CLI `main()` still asks location last in its own interactive question order.
  Confirmed NOT a bug: it is explicitly a testing tool for the ontology/template wiring (its own
  --help says so), not the emergency flow, and `build_briefing`/`render_briefing` just joins the
  same chunks the app uses - it inherited the location-first order automatically.

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

**Target scenario (WIDENED 2026-08-20 - see the location-neutral pass below):** ANY INDOOR PLACE
WITH A FIXED, REGISTERED ADDRESS, where the people present may not speak Japanese. A household
with a known at-risk person is the obvious case, but a company dormitory, care facility, language
school or share house work IDENTICALLY - the only requirement is that the address in profile.json
is the address of the building the device sits in.

**Physical setup - TWO DEVICES:**
- Phone: dials 119, on SPEAKERPHONE.
- Fixed device (laptop/tablet) that STAYS IN THE BUILDING: runs this app, ALREADY OPEN, warm.
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

**Honest scope limit, state it in the pitch:** this does not help someone alone, OUTDOORS, or in
a building that has not been set up. It is an INDOOR emergency tool for a registered address.
Narrower than "helps foreigners call 119" - and far stronger, because every design decision
already fits it (stored address, stored patient profile, stored conditions, warm model).

**WHY INDOORS IS THE RIGHT SCOPE, NOT A RETREAT (verified 2026-08-20).** Japan already handles
the outdoor/mobile case BETTER than we could, with two pieces of national infrastructure:

1. **緊急通報位置通知** - dialling 119 from a mobile transmits the caller's location to the fire
   department AUTOMATICALLY, at carrier level, nationwide (confirmed on Docomo's and SoftBank's
   own service pages). Adding GPS to this app would duplicate that, worse: a laptop has no GPS
   receiver, WiFi positioning needs the internet, and no coordinate can give a room number.
2. **三者間同時通訳** - a live professional interpreter patched into any 119 call, 24/7, any
   phone, no app, no registration. 673/720 fire departments = 93.5% (FDMA, Jan 2025).

What NEITHER supplies is the ROOM NUMBER and the PATIENT'S MEDICAL HISTORY. Carrier location
finds the building, not 405号室. An interpreter faithfully translates what the caller CAN say -
not what they cannot recall, spell or pronounce under panic. That gap exists only where an
address can be registered in advance, i.e. indoors.

=> The honest claim is NOT "this helps foreigners call 119" (the government largely solved that).
It is **"this delivers a verified patient record into the first 15 seconds of the call."**

This also RETIRES the "not at home" problem rather than solving it: away from the registered
address every advantage this app has evaporates, and the caller is better served by the two
systems above, which need no device at all. The app says 「今、別の場所にいます。」 and gets out
of the way.

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

## PANIC/DISFLUENCY - tested at last, 2026-08-14 (benchmark/eval_disfluent.py)

Accent was tested months ago (L2-ARCTIC). Panic never had been, at any stage. Same 52 labelled
cases, each perturbed with the three things panic does to speech - word repetition, stuttered
false starts, and filler ("oh god", "please hurry") - then re-scored against the same labels.

                 exact        precision   recall   F1     fabrications
    CLEAN        50/52 (96%)  1.00        0.96     0.98   0
    PANICKED     50/52 (96%)  0.96        1.00     0.98   2

**Disfluency does NOT break classification.** Exact-match and F1 are identical. That is the
first evidence either way on the thing we had been most worried about.

**But precision 1.00 does not survive panic - it falls to 0.96, with 2 fabrications.** The
pattern is coherent: noise makes the model OVER-include, so recall rises to 1.00 while precision
falls. It errs toward too many symptoms rather than too few, which is the safer direction, but
"zero fabrications" is an ENGLISH, CLEAN-SPEECH claim and should be stated that way.

The two failures:
  "her stomach is- is killing killing her, she's doubled over" -> added `vomiting`
  "he's- he's just really anxious and panicking panicking about work" -> returned `confused`
The second is partly an artefact: the harness wraps every case in panic filler, and that case is
ABOUT someone panicking. The first is a genuine repetition-induced fabrication.

HONEST BOUND: this perturbs TEXT. Real panic also degrades the AUDIO before Whisper sees it, so
this is a lower bound - passing does not prove robustness, failing would have proven fragility.

**Baseline also improved and the old note below is stale:** the recorded 40 cases / 90% exact /
F1 0.94 is now 52 cases / 96% exact / F1 0.98, from the ontology work since.

## NON-ENGLISH WAS BROKEN - found and fixed 2026-08-14

The language selector offered 9 languages. Nobody had ever run one end to end. Two were tested:

    Chinese  transcript correct  ->  classified []           EVERY symptom silently dropped
    Korean   transcript correct  ->  classified no_pulse     FABRICATED cardiac arrest

Whisper was fine both times. The CLASSIFIER failed: its system prompt, few-shot examples and all
29 trigger phrases are English, and we handed it Chinese with no bridge. Precision 1.00 was
measured on English only; the first Korean test invented the most dangerous term in the ontology.

**FIX:** for a non-English caller, run Whisper TWICE over the same audio.
    transcribe -> the caller's own language. What they READ and confirm (the safety loop only
                  works if they can read it).
    translate  -> Whisper's built-in English output. What the CLASSIFIER reads.
After the fix both Chinese and Korean returned the correct `collapsed` + `chest_pain`, and the
`no_pulse` fabrication was gone.

**CAVEAT, unresolved: TRANSLATE MODE LOSES NEGATION.** Both clips said "there is no response";
both came back as the opposite. That inversion did NOT reach the briefing - consciousness is in
SLM_DISCARD and comes from a forced button. **The architecture caught a failure it was designed
for, arriving by a completely different route than anticipated.** But the same corruption could
hit a symptom that is not excluded, and the interpretation-confirmation screen is the only
remaining backstop - and its labels are English, which is weakest for exactly these callers.

Still untested: the other 7 languages, and Whisper is known to be weakest on some (Nepali,
Burmese) whose speakers are most vulnerable. Do not claim uniform coverage.

## PRE-RENDERED AUDIO - the TTS portability answer (2026-08-14)

The app no longer synthesises speech at runtime. `tools/build_audio.py` renders every sentence
it can ever say into data/audio/ (44 sentences, 3.3 MB); `speak_japanese()` plays files and only
falls back to live TTS if one is missing.

Possible ONLY because the ontology is closed - the same property the safety design rests on.
Fixed lines are constants, the 29 terms are a closed set, and profile lines are settled when the
profile is written. Multi-symptom chunks are handled by splitting on 。 and concatenating, so
COMBINATIONS never need rendering.

Buys: identical audio everywhere; **the Windows SAPI5 Japanese-language-pack risk disappears
entirely** (it was the single biggest demo-breaking unknown); no synthesis during an emergency;
no extra model in memory.

**PRIVACY SPLIT:** data/audio/profile/ holds the address, name, age and conditions SPOKEN ALOUD.
Gitignored - committing it would leak a real home address as audio, exactly what excluding
profile.json prevents for text. The 40 shared sentences ARE committed.

`tools/setup_profile.py` is the pre-registration step: prompts for each field, writes
profile.json, and re-renders the changed audio automatically. Fails loudly if the machine has no
Japanese voice, telling you to build elsewhere and copy data/audio/ across.

## LATENCY BREAKDOWN - measured 2026-08-14 (Mac, OpenVINO INT8, 3B)

    MODEL LOAD (once, at app open) : 59.1s
    STAGE A prompt                 : 788 tokens
    STAGE A (pick candidates)      : 14.5s
    STAGE B (review/trim)          :  1.5s
    TOTAL user-visible wait        : 16.0s

**Stage A is 90% of the wait; Stage B is nearly free.** That settles the recurring question of
whether the verification pass is worth its cost - 1.5s for precision 1.00 is a bargain, and any
future optimisation should leave it alone and attack Stage A.

**WHY Stage A is slow, and the fix it points at:** the prompt is 788 tokens, and ~700 of those
are the 29-entry menu plus few-shot examples - IDENTICAL on every single call. Only the caller's
transcript (a few dozen tokens at the END) ever changes. So we re-process the same ~700 tokens
from scratch every time.

=> **PREFIX / KV CACHING is the obvious win.** Process the static prefix once at warm-up, keep
   the KV state, and feed only the transcript per call. Architecture-preserving: same model,
   same two stages, same prompts, same accuracy. Check whether optimum-intel/OpenVINO exposes
   reusable `past_key_values` for this. Untried.

Other levers, weaker: trim trigger phrases per entry (shorter menu, may cost accuracy);
max_new_tokens 64 -> 32 for Stage A (the JSON array is short); and of course the Intel/OpenVINO
numbers themselves, still unmeasured for the SLM.

**59s model load confirms the operational rule: NEVER restart the app right before a demo.**
Harmless in the real use case (it sits open all day), fatal on stage.

## UI PRINCIPLE - the screen must guide, never present (founder, 2026-08-14)

Standing rule for every screen, not a one-off note:

**A lot of text appearing at once causes subconscious confusion.** The caller is panicking. They
should be close to autopilot - one clear thing to do per screen, no reading, no deciding. We want
SWIFTNESS. Anything that makes them stop and parse the screen is a defect, even if every word on
it is correct.

Applied so far: dropped the "Ambulance + location — this is what sends help" caption (explained
OUR reasoning to a panicking user); toggle -> radio for the location question; per-symptom aspect
radios given explicit names; handoff screen stripped to Japanese only. Judge new screens by this,
and prefer removing a line to adding one.

## Memory footprint - FUTURE enhancement, explicitly not for the competition (2026-08-13)

Raised by the founder. Currently ~3 GB resident (Qwen2.5-3B, OpenVINO INT8) plus Whisper small.
Explicitly parked as "later" - it does not block the competition.

**First, a correction that reframes the problem.** The founder's intuition was "Claude/ChatGPT are
huge yet run smoothly on my device, so there must be a trick". They do NOT run on the device at
all. They run in datacentres on racks of GPUs; the phone or browser is a thin client sending text
over a network. That is why they feel light - none of the work happens locally.

Kyūkyū-Bridge runs the model ON the device, offline, with no network. That is a strictly harder
engineering problem AND the entire product thesis: an emergency tool that needs a working
internet connection is not an emergency tool. So the comparison is not us-versus-them; they are
solving a different problem. Do not adopt their architecture - it would destroy the offline
guarantee.

**Real levers, cheapest and lowest-risk first:**
1. **INT4 instead of INT8 weight quantization.** Same model, same architecture, same code path -
   roughly halves memory (~3 GB -> ~1.5-1.8 GB). One flag in convert_slm.py
   (OVWeightQuantizationConfig(bits=4)). Costs some accuracy, so it MUST be re-measured on
   benchmark/eval_slm.py before adopting. This is the obvious first experiment.
2. **A smaller model with task-specific fine-tuning.** A 0.5B model fine-tuned on THIS narrow
   classification task can beat a general-purpose 3B at it. Needs training data - we have ~120
   labelled cases across the three test sets, which is thin but a starting point.
3. **Knowledge distillation** - train a small model on the 3B's outputs. Bigger project.
4. **Pruning / sparsity.** Least mature, most effort, skip unless the above are exhausted.

**Ordering:** try INT4 first and measure. It is a one-line change with a measurable answer, and
if accuracy holds it halves the footprint for essentially no work. Everything else re-opens the
accuracy question that Stage A + Stage B already settled (see below), so it needs the eval
harness pointed at it before anything ships.

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

## Needs a Japanese speaker - ALL RESOLVED (2026-08-14)

- ~~All 16 `japanese_term` values~~ - RESOLVED. All **29** are founder-verified as of 2026-08-12,
  reviewed as rendered output rather than raw strings, which is what caught the
  polite-form-before-と言っています bug and the 脈がありません over-claim.
- ~~The label `通報者の説明：`~~ - RESOLVED. Replaced by the natural lead-in `あと、`.
- ~~The fallback `詳細不明`~~ - RESOLVED. The symptom line is omitted entirely when nothing
  matches, rather than announcing an empty field.
- Founder-worded since: the dispatcher line (すみません。日本語がわからないので…), the
  particle rule (意識はあります positive / 意識がありません negative), and the four handoff
  labels (患者 / 持病 / 症状 / 通報者).
- Specific term questions remain recorded in the `note` fields inside `ontology.json`.

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
  our internal concept. Then 「今、自宅にいません。」, now 「今、別の場所にいます。」 after the
  2026-08-20 location-neutral pass (自宅 hard-coded a home assumption into the one line the
  dispatcher hears, and was simply false when the registered address is a dormitory). Marked
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
