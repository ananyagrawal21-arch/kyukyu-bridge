# LLM COUNCIL TRANSCRIPT — Kyūkyū-Bridge real-world use case
**Date:** 2026-09-14 · **Session:** rebuild of the real-world use case under a hard constraint

---

## 1. THE ORIGINAL QUESTION (founder)

> "You need to council kyukyu bridge. Make sure that after the council has finished its discussion
> and presents me the results, the real-us-case must be: (1) Absolutely realistic, practical and
> feasible (2) Absolutely crystal clear execution must be possible and feasible, considering my
> location, situation etc. (3) There should be no room for negotiation or comforting or adjustment.
> We don't want to compromise ourselves with expecting panicked users to arrange 2 phones at once,
> one for 119 and one for the app."

Clarified by the founder before framing:
- **The constraint, in his words:** "I don't expect any user to have a device at home already warm,
  and I don't expect any user to be forced to operate 2 devices in a situation of panic, where one
  is for dialing 119 and the other is for this app."
- **His situation:** high schooler, Indian, living in Japan; scaling advice must be grounded there.
- **Stakes:** both deployment and the Intel AI Global Impact Festival; deployment is wanted ASAP and
  is *not* for the judges; the pitch must follow the truth, never shape it.
- **Deadline:** assume one week.
- **First install:** own household. Beyond that, zero.
- **Form factor:** deliberately undecided — derive it from the use case.
- **Expert validation:** no realistic access to a paramedic or dispatcher; local fire department
  rated 99.9% infeasible.

---

## 2. THE FRAMED QUESTION

See `framed-question.md` (reproduced in full in the appendix of this file's sibling report).
Core mandate handed to all five advisors: the rewritten use case must be absolutely realistic,
crystal clear, and contain no room for negotiation or comfort. Both load-bearing assumptions —
the always-warm in-building laptop, and the panicking caller aiming a speakerphone at it — were
declared dead unless resurrected with something better than optimism. Advisors were explicitly
permitted to change *what* the app delivers, not only *how*.

---

## 3. ADVISOR RESPONSES

### The Contrarian
The single-device path is not "untested," it is adversely designed against you. On a speakerphone
call, hardware AEC's reference signal is the speaker feed, not the downlink stream. Your app's
media audio goes into that same mixer. You would be asking the phone's DSP to cancel everything
coming out of its loudspeaker except the one thing you want it to pass. Worse, the mic is
centimetres from a speaker at call volume: AGC clamps, and the caller's own voice is destroyed for
the duration. On iOS, media playback during a cellular call is ducked or denied outright. Even in
the lucky case where one handset leaks enough signal through, you have a life-safety product whose
delivery mechanism is per-handset, per-OS, per-carrier lottery. "It worked on my Pixel" is not a
mechanism. Test it — but plan for it failing, because it probably will, and an unreliable pass is
worse than a clean fail.

Here is the flaw you're avoiding. Strip out live injection and look at what's left. Your own log
(line ~1838) concedes a government text+GPS app beats you architecturally. Your README says the
only real gap versus 三者間同時通訳 is the room number and the medical history. That gap is a
profile.json lookup and a pre-rendered string. It needs no Whisper, no Qwen, no ontology, no
OpenVINO, no 511s→73s. The part of your product that is uniquely valuable requires zero AI. The
part that requires AI — live symptom classification into 31 terms — is precisely the part a human
interpreter already does better, live, on 93.5% of departments, for free.

So yes: a laminated card with your address, 101号室, age, 持病, in Japanese with romaji the caller
can read aloud, delivers most of your defensible value at 0% of the technology. Say that out loud
before a judge says it for you.

Honest fallback: the app becomes a generator of that pre-call artifact — one phone, no call-time
audio path, nothing to inject, no AEC. The AI earns its place only if it does something the card
cannot: 口頭指導 in the caller's language, spoken to the caller's ear, after dispatch. That's a
delivery-to-caller problem, which has no technical wall.

Also delete: "the app runs on a device that stays in the building" (README line 80), and stop
claiming you attack the 3–6 min on-scene delay — that clock starts after your window closes.

### The First Principles Thinker
Strip the AI out and count what's left: 46 WAV files, 3.9 MB. That is the entire Japanese surface
area of this product — every sentence it can ever utter, pre-rendered by `tools/build_audio.py`,
human-verified, closed-set. The classifier does not produce Japanese. It picks which file to play.
The irreducible unit of value is a verified Japanese audio sentence, and there are 46 of them.

Now count the bits. At the moment of the call: address, room, age, sex, conditions — all already in
profile.json. Zero entropy. Consciousness, breathing, circulation — forced buttons, 3 bits, the
model is explicitly banned from touching them. What remains is one selection from symptoms (20)
plus events (8): roughly 4–5 bits of genuinely new information.

The product runs Whisper, then a 3-billion-parameter model over an 884-token prompt, then two
confirmation loops, to move five bits. That is the whole thing. OpenVINO's 6.97× and the
x64-exclusive 10.94× are real engineering — applied to hauling five bits across a laptop.

So the council is being asked the wrong question. "One device or two?" is downstream. The real
question is: why is there a speech input at all?

Your own README answers it against you: "a panicking person cannot produce structured,
dispatcher-usable information at all — in any language." Correct. The response to *cannot produce
structure* is to hand them the structure, not to infer it from unstructured speech. Speech
re-injects exactly the entropy the stored profile was built to eliminate — and every open risk you
logged lives in that lane: C1 negation inversion ("the most dangerous open item in this file"),
C2's seven unrun languages, Whisper's "You're free to go." ×70, the English-only confirmation
screens.

A 28-icon grid moves those five bits in two taps. No STT. No translation. No negation loss. No
fabrications. No warm model — which kills warm_brain(), the two-device assumption, and the 3.9 GB
footprint in one cut. It fits in the phone already in the caller's hand.

And a laminated fridge card does not substitute, because a caller who cannot read Japanese cannot
pronounce 〇〇区〇〇. The real product is an offline Japanese soundboard with a stored profile. Say
that out loud. Then decide, honestly, whether the Intel story survives it — not the reverse.

### The Expansionist
The 3.9 GB is not the product. The 4.1 MB is.

Everyone is reasoning as if the asset pile is a model stack. It isn't. `data/audio/` is 46
pre-rendered WAVs, 3.9 MB, and `data/ontology.json` is 31 human-verified terms plus 27 conditions
and 13 condition groups. Neither needs Whisper, Qwen, OpenVINO, or a warm anything. The README
already concedes the app "never synthesises speech at runtime." That means the inference can happen
once, at registration, on a machine that is not the user's — the founder's laptop, in a school hall
— and the household walks away with a phone-sized bundle of verified Japanese audio keyed to their
address, their room number, their grandmother's anticoagulants. The hard constraint kills the
runtime. It does not touch the output. Registration is where the AI earns its keep, and
registration has no panic, no clock, and no second device.

That reframes everything downstream. OpenVINO's 6.97× and the x64-only 10.94× prefix caching stop
being a home-laptop requirement and become the reason one person can register 200 households in a
weekend — batch throughput on the operator's Intel machine. The Intel story survives the constraint
by moving, not dying.

Concretely, Nishikasai: the Indian International School in Japan sits in Nishikasai with roughly a
thousand families, almost all within walking distance, and its parents are precisely the README's
user — foreign resident, fixed registered address, elderly relative visiting on a dependent visa,
poor Japanese. One PTA-hall session is not "community partnership," it is a folding table, a
laptop, a Hindi-speaking high schooler, and a queue. Add the Edogawa Diwali/Namaste India crowd at
Kasai Rinkai and the Nishikasai grocers (Spice Magic, TMVS) as QR-sticker surfaces.

And the expert gap is a web form, not a wall. 葛西消防署 runs free public 普通救命講習 on open
enrollment — three hours in a room with a serving firefighter instructor. C8 says no paramedic has
ever seen this. Booking that course changes C8 this month, without asking permission from anyone.

Undervalued most: the ontology itself. No public dataset maps panicked bystander speech to
dispatcher-register Japanese. Publish it CC-BY — it outlives the app.

### The Outsider
What I picture, and where it breaks. Someone collapses. A person dials 119, puts the phone on the
floor on speakerphone, and then — walks to another room, to a laptop, and starts tapping through
screens while a dispatcher is talking. That is the break. The README never says where the laptop
is. Emergencies happen in bathrooms, bedrooms, kitchens, stairwells; a laptop that "stays in the
building" is in exactly one of those. The document treats "in the building" as if it means "within
arm's reach." It doesn't. Nobody stands next to the laptop when the emergency starts, and nobody
leaves the patient to go find it.

What a real person does at 3am. They dial 119 and shout in English. Then they call the one
Japanese-speaking person they know — a neighbour, a colleague, a spouse's friend — and hand the
phone over. That's the actual incumbent, and the README never mentions it. It compares itself to
government services, not to the thing people really do.

What I don't believe. The room-number claim is the load-bearing justification for the whole thing,
and it's a three-digit number. A terrified person who can't pronounce 呂律が回らない can absolutely
say "four zero five." If room number is the gap, a fridge magnet closes it.

The document contradicts itself. It says the ambulance is dispatched at 15 seconds and everything
after happens while it's en route — then says "inference latency is a polish problem, not a safety
one." Fine. But then the 6.97× Intel speedup is a polish story, and it gets four times more page
space than what the user actually touches. As a stranger, the ratio of Intel prose to human prose
tells me what this was built for.

English interface. The pitch is "for people who don't speak Japanese," but the screens are English.
So the user is an English speaker. Say that plainly — the 13.3%-can't-read-Japanese statistic is
doing work the product doesn't do.

The problem I'd name. Not the first 60 seconds. The nine minutes after, when a dispatcher is trying
to talk you through CPR in Japanese and you understand none of it. The README lists that as out of
scope in one line. That's the frightening part, and it's the part left alone.

### The Executor
Run the echo test tonight. It gates everything and costs ten minutes.

Protocol, exactly: Phone A calls Phone B. B goes in another room with someone holding it. A on
speakerphone, media volume max. Play `data/audio/03f4fc3c57a080a2.wav` (or any fixed line) out of
A's own loudspeaker while the call is live. Listener on B reports: clear / faint-and-warbling /
silent. Repeat three times — A flat on a table, A held up, and with someone talking near A. Then
repeat the whole thing on the other OS. AEC is implemented differently by Apple and by each Android
OEM; one phone proves nothing.

Reading the result: clear → single device works, the laptop dies, the form factor is a PWA.
Faint/chopped/pumping → AEC is gating it; retest with wired earbuds in A (the AEC reference moves
off the loudspeaker) — if that recovers it, the product ships with "plug in earbuds," which is a far
smaller ask than "own a warm laptop." Silent → the single-device acoustic loop is dead, and you stop
designing around it today.

Re-platforming, priced against the actual code: a full port is impossible this week and you should
stop considering it. `app.py` is 1,161 lines of Streamlit `session_state` spaghetti; `src/` is
another ~2,400. Worse, Android means no OpenVINO — prefix caching is x64-only, so the 10.94×
vanishes — and Whisper + Qwen2.5-3B on a phone is a llama.cpp/ONNX port measured in weeks, not days.

But you don't need the models to ship the phone version. `data/audio/` is 46 WAVs, 3.9 MB, a closed
set. 救急です + your address + 28 symptom/event terms are already rendered. A static PWA with 31
tap-buttons and `<audio>` playback is two evenings of HTML/JS and delivers the dispatch-critical
payload with zero AI on the phone already in the caller's hand.

Seven days. Mon: echo test, both OSes, write the result into OPEN_DECISIONS.md before you touch
code. Tue–Wed: build the tap-only PWA. Thu: install it on a real phone, run five timed drills with
your family, stopwatch to "address delivered." Fri: laptop app becomes the demo rig for the
Intel/OpenVINO story — keep it, benchmark it, don't ship it. Sat: pitch rewritten to the truth.
Sun: buffer.

Cut: the 7 untested languages, the folium map picker, 口頭指導/CPR, the ontology expansion (D2),
Japanese UI localisation.

Validation you can get by Friday: book a 救命講習 at our ward or Edogawa fire station — public, free,
walk-in-bookable, and a serving firefighter is in the room for three hours. Show it in the break.
That is your paramedic. Also: any Nishikasai clinic doctor, and the Indian school's office — ask for
ten households, not one.

---

## 4. ANONYMISATION MAPPING (revealed)

| Letter | Advisor |
|---|---|
| A | The Outsider |
| B | The Executor |
| C | The Contrarian |
| D | The Expansionist |
| E | The First Principles Thinker |

---

## 5. PEER REVIEWS

### Reviewer 1 — technical / physics lens (fact-checked against the repo)

**Verification first**

| Claim | Verdict |
|---|---|
| "46 WAVs, 3.9 MB" (B, D, E) | **Wrong count.** 49 WAVs, 4.0 MB (44 in `data/audio/` + 5 in `data/audio/profile/`). |
| `app.py` 1,161 lines (B) | Exact. `src/` is 2,089 lines, not "~2,400" — inflated ~15%. |
| Ontology "31 + 27 + 13" (D) | Correct. E's "28-icon grid" also correct. |
| 884-token prompt (E) | Correct, README:260. |

1. **Strongest: D.** Not for rhetoric — because verification proves its thesis is already built.
   `data/audio/profile/` contains five per-household WAVs rendered at build time. D's "inference
   happens once, at registration, on a machine that is not the user's" isn't a proposal; it's the
   existing architecture, unnoticed by everyone including D. E's bit-count is the sharpest reasoning
   in the set, but D's survives the hard constraint *and* keeps OpenVINO honest as batch throughput.
2. **Biggest blind spot: A.** It never touches a mechanism. No AEC, no codec, no form factor, no
   device. It delivers zero of the six mandated outputs — a critique of the README, not an answer.
   Its one real contribution (the Japanese-speaking neighbour is the true incumbent) deserves
   salvaging.
3. **All five missed: B's decisive test is codec-confounded.** Phone-to-phone VoLTE negotiates
   AMR-**WB** (~50–7000 Hz). A 119 call routinely lands on AMR-**NB**, 300–3400 Hz, *with a voice
   activity detector*. Loudspeaker-to-mic TTS under AGC clamping is exactly the signal a VAD
   misclassifies as noise and replaces with comfort noise — a failure mode independent of AEC, which
   nobody named. "Clear over a VoLTE call → ship the PWA" is an invalid reading.

### Reviewer 2 — human factors / real emergency lens

1. **Strongest: B.** The only response that treats the unknown as an experiment rather than a
   position, and the only one that proposes measuring *humans* — five timed drills, stopwatch to
   "address delivered." Its earbuds fallback is the best human-factors insight in the set: it
   converts an impossible prerequisite ("own a warm laptop") into a cheap one. C is the sharpest
   reasoning but its conclusion is a posture; B's is a schedule.
2. **Biggest blind spot: E.** "Two taps" is asserted, never tested. Under adrenaline fine motor
   control degrades, the screen is held one-handed while the other hand is on a chest, and a 28-icon
   grid is a mistap surface. E has no undo: a wrong tap speaks confidently wrong Japanese in an
   authoritative synthetic voice, and neither the caller (who can't hear the error) nor the
   dispatcher (who can't know it's wrong) can catch it. E also dismisses the card because a caller
   can't pronounce 〇〇区〇〇 — while asking that same caller to drive a grid mid-call.
3. **All five missed the duplex problem.** Every proposal plays audio *at* a dispatcher who can talk
   back. Nobody specified a stop button, barge-in, or what happens when the dispatcher interrupts a
   WAV mid-sentence — a recording cannot yield, and a dispatcher who cannot interrupt will talk over
   it, so neither party hears the other. Nobody addressed that playback occupies the caller's only
   audio channel: while Japanese plays, the caller cannot hear the dispatcher's question. And nobody
   asked what a dispatcher does on hearing a synthetic voice — suspected prank, or a question the
   grid cannot answer.

### Reviewer 3 — strategic / festival-and-truth lens

1. **Strongest: B.** The only response satisfying both mandates without rationalising. It gates the
   decision on a ten-minute test *before* code, prices re-platforming against actual line counts,
   ships a tap-only PWA from existing WAVs, and keeps the laptop as a benchmarked demo rig rather
   than pretending the Intel work vanished. It also converts C8 from "wall" to a bookable 救命講習.
   E is the most honest response — it alone says "decide whether the Intel story survives it, not
   the reverse," which is the founder's own rule stated as a method — but B leaves him something to
   show on day seven.
2. **Biggest blind spot: C.** Brave-sounding, terminal. It argues the laminated card carries the
   defensible value, then hands him a pre-call artifact generator — no submission, no demo, no
   measurable install. E refutes it in one line C never anticipates: a caller who cannot read
   Japanese cannot pronounce 〇〇区〇〇. C mistakes "the AI is unnecessary" for "the product is
   unnecessary."
3. **All five missed:** D's rescue — "the AI runs at registration" — is a rationalisation as stated.
   Registration-time work is TTS of an address, not Qwen classification; the 6.97×/10.94× were
   measured on the *inference* path that registration doesn't use. Batch-registering 200 households
   does not consume that speedup. And nobody named the strongest honest festival framing available:
   *we ablated our own model and measured that five bits didn't need it.* A rigorously documented
   negative result is judgeable. Hiding it is the only thing that isn't.

### Reviewer 4 — deployment and liability lens

1. **Strongest: C.** The only response that reasons about failure modes rather than success paths:
   "an unreliable pass is worse than a clean fail" is the correct liability instinct for a
   life-safety product. Its fallback removes the live-call failure surface entirely, so there is
   nothing to misfire at second 30. It is also the only response treating false marketing claims as
   a liability rather than a tidiness issue. B is the most executable but designs for shipping, not
   for the day it fails.
2. **Biggest blind spot: D.** "One person can register 200 households in a weekend" is a 16-year-old,
   unsupervised, collecting 要配慮個人情報 — conditions, medications, ages of elderly dependents —
   from strangers at a school hall. D never mentions consent, APPI, who is the data controller, where
   profile.json lives, or that a minor cannot sign a data agreement. It also calls expert validation
   "a web form": a three-hour CPR class yields no review, no sign-off, no cover. D converts the
   single genuine liability event into a throughput metric.
3. **All five missed:** nobody asks what happens the first time it runs badly. No incident record, no
   way to learn it was used at all, no recall path when a household moves and the stored address is
   now wrong, no "if this fails, hang up and speak" instruction, no adult sponsor or teacher of
   record. Also unconsidered: a dispatcher hearing synthetic Japanese may treat the call as a prank.

### Reviewer 5 — convergence and dissent lens

1. **Strongest: B.** The only response that converts the central unknown into a falsifiable test with
   a protocol, a decision rule per outcome, and a fallback (wired earbuds moving the AEC reference)
   nobody else thought of. C asserts the same physics confidently but from armchair DSP reasoning —
   "it probably will fail" is a prediction, not a result.

   **Interrogating the consensus.** Four responses converge because they all ran the same cheap move:
   subtract the AI, find the residue, declare the residue the product. That move always terminates
   somewhere, so agreement here is weak evidence. The steelman nobody wrote: speech is not a faster
   input, it is a *different* one. A caller doing compressions has hands occupied and eyes on the
   patient; tapping demands both. And a panicking layperson does not know which of 28 categories
   "she's gone grey and floppy" belongs to — mapping free description onto ontology IDs is precisely
   the classifier's job, and E's grid silently hands that mapping back to the user while claiming to
   "hand them the structure." Twenty-eight alternatives under stress is search, not structure.

   **Most consequential disagreement:** C ("laminated card delivers most of the value") vs E ("a
   caller who cannot read Japanese cannot pronounce 〇〇区〇〇"). **E is right** — romaji read aloud
   by a panicked non-speaker through narrowband AMR is not intelligible, and that single fact is what
   keeps a device in the loop at all.
2. **Biggest blind spot: A.** Its diagnosis is the sharpest in the set — it alone names the real
   incumbent (hand the phone to a Japanese-speaking neighbour) and the real terror (the nine minutes
   of untranslated 口頭指導). But it delivers nothing the mandate asked for. It indicts and leaves.
3. **All five missed: the downlink.** Every response treats the problem as getting information *to*
   the dispatcher. But a 119 dispatcher immediately talks *back* — scripted Japanese questions the
   caller cannot understand — and that failure happens inside the same 60 seconds, needs no uplink
   injection, breaks no physics, and is the one job where on-device STT plus the ontology genuinely
   earns its runtime. Second omission: nobody proposed measuring icon-find latency in B's Thursday
   drills, so the consensus ships its core assumption untested — the same sin it convicts the laptop
   of.

---

## 6. CHAIRMAN SYNTHESIS

*(reproduced in full in `council-report-2026-09-14.html`)*
# COUNCIL VERDICT — Kyūkyū-Bridge real-world use case
**2026-09-14 · 5 advisors, 5 peer reviews, chairman synthesis**

---

## Where the Council Agrees

**1. The warm-laptop, two-device use case is dead, and not by your instruction — by its own logic.**
All five advisors independently killed it. The Outsider gave the reason the document never
addressed: the README says the laptop "stays in the building," and treats that as if it meant
*within arm's reach*. It doesn't. Emergencies happen in bathrooms, bedrooms, stairwells. Nobody
stands next to the laptop when someone collapses, and nobody leaves the patient to go find it.
Your constraint was correct before you justified it.

**2. Almost none of the emergency-path value requires a model at runtime.**
The First Principles Thinker counted the bits and the count is not arguable. Address, room, age,
sex, conditions: already in `profile.json`, zero entropy. Consciousness, breathing, circulation:
forced buttons, and the model is explicitly *banned* from touching them. What is left for Whisper
plus a 3-billion-parameter model over an 884-token prompt is **one selection out of 28 — roughly
five bits.** That is the entire job the runtime AI does on a live call.

**3. The real deliverable is already built and it is 4 MB, not 3.9 GB.**
49 pre-rendered WAVs (verified: 44 in `data/audio/`, 5 in `data/audio/profile/`) and a 31-term
human-verified ontology. The README already concedes "the app never synthesises speech at runtime."
The classifier does not *produce* Japanese — it picks which file to play. Everything defensible
about this product is a file lookup and a WAV.

**4. The form factor that follows is the phone already in the caller's hand.**
Not a laptop, not a tablet, not a second anything. An offline PWA holding that household's audio
bundle.

**5. C8 is not a wall, it is a booking form.**
our ward and Edogawa fire stations run free, publicly-enrollable 普通救命講習 — three hours in a room
with a serving firefighter. You rated expert access 99.9% infeasible. You were wrong, and this is
the cheapest correction available to you this week.

**6. A full re-platform in seven days is impossible and you should stop considering it.**
Verified: `app.py` is 1,161 lines, `src/` is 2,089. Porting Whisper + Qwen2.5-3B to a phone is
weeks of llama.cpp/ONNX work, and it destroys OpenVINO (prefix caching is x64-only). You do not
need to. The WAVs are already rendered; a tap-driven PWA over a closed audio set is HTML and
`<audio>`.

---

## Where the Council Clashes

**Clash 1 — Does a laminated card make the whole product unnecessary?**
The Contrarian's sharpest attack: the only gap you claim over 三者間同時通訳 is the room number and
the medical history, and a laminated fridge card with your address in Japanese plus romaji delivers
that at 0% of the technology. The First Principles Thinker refuted it in one line and the dissent
reviewer confirmed it: **a caller who cannot read Japanese cannot pronounce 〇〇区〇〇.** Romaji
read aloud by a panicked non-speaker through narrowband cellular is not intelligible. *That single
fact is the only thing keeping a device in the loop at all — and you should be able to say it in
one breath, because it is now the load-bearing justification for your entire product.*

**Clash 2 — Tap grid versus speech input. This is the genuine one, and the consensus is suspect.**
Four advisors converged on "strip the AI, ship a tap grid." The dissent reviewer was right to be
suspicious: four instances running the same cheap move (subtract the AI, find the residue, declare
the residue the product) is weak evidence, not strong. The steelman nobody wrote: **a panicking
layperson does not know which of 28 categories "she's gone grey and floppy" belongs to.** Mapping
free description onto ontology IDs is *precisely* the classifier's job, and a grid silently hands
that mapping back to the user while claiming to "hand them the structure." Twenty-eight
alternatives under stress is search, not structure. The human-factors reviewer added the other
half: a wrong tap speaks confidently wrong Japanese in an authoritative synthetic voice, and
neither the caller nor the dispatcher can catch it.

**Chairman's resolution, and it dissolves most of the clash:** the panic-critical payload is **one
button**, not 28. Your own README already says the ambulance is dispatched on type + location at
~15 seconds. Every symptom tap happens *after* dispatch, while the ambulance is already moving,
when panic has dropped and a dispatcher is on the line guiding. So "28 icons under maximum stress"
is a scenario your own architecture does not actually create. Ship the grid — but the drill must
measure time-to-**first-button**, and separately measure icon-find latency, or you are shipping
your core assumption untested, which is the exact sin you are convicting the laptop of.

**Clash 3 — Does gutting the runtime AI destroy the Intel festival story?**
The Expansionist's rescue was "the AI moves to registration." The strategy reviewer called that a
rationalisation and is right: registration-time work is **TTS of an address, not Qwen
classification**, and your 6.97× / 10.94× were measured on the inference path registration never
touches. Do not use that framing — it will not survive a judge who reads your own benchmark files.

---

## Blind Spots the Council Caught

**A. The decisive test, as proposed, is invalid.** Phone-to-phone VoLTE negotiates AMR-**WB**
(~50–7000 Hz). A real 119 call routinely lands on AMR-**NB** (300–3400 Hz) **with a voice activity
detector**. Loudspeaker-to-mic TTS under AGC clamping is exactly the signal a VAD misclassifies as
noise and replaces with comfort noise — a failure mode entirely independent of echo cancellation,
which nobody named. **This also invalidates your existing "PASSED" result:** item 13 in
`OPEN_DECISIONS.md` was a **WhatsApp** call — wideband Opus, no cellular VAD. That test does not
prove what the register says it proves.

**B. The duplex problem. Nobody in the entire council designed for the dispatcher talking back.**
A recording cannot yield. A dispatcher who cannot interrupt will talk over it, and then neither
party hears the other. Worse: while Japanese plays out the loudspeaker, **the caller cannot hear
the dispatcher's question** — playback occupies their only audio channel. There is no STOP button
anywhere in any proposal.

**C. The downlink is the real unsolved problem, and it is where runtime AI genuinely earns its
place.** Every advisor treated this as getting information *to* the dispatcher. But a 119 dispatcher
immediately talks *back*, in scripted Japanese the caller cannot understand — inside the same 60
seconds. That failure needs **no uplink injection, breaks no physics, and works on one device.**
The Outsider named the same thing from the other end: the frightening part is the nine minutes of
口頭指導 you dismiss in one line. **This is your next product, and naming it is what makes the
ablation an advance rather than a retreat.**

**D. Liability, which no advisor raised and one reviewer demolished.** "Register 200 households in
a weekend" is a 16-year-old, unsupervised, collecting **要配慮個人情報** — conditions, medications,
ages of elderly dependents — from strangers in a school hall. No consent form, no APPI data
controller, no stated storage location, and a minor cannot sign a data agreement. Beyond that:
there is no incident record, no way to ever learn it was used, no recall path when a household
moves and the stored address becomes wrong, and no instruction telling the caller what to do when
it fails.

**E. The real incumbent is missing from your competitive analysis.** Not NET119, not 三者間同時通訳.
It is: *dial 119, shout in English, then phone the one Japanese-speaking person you know and hand
over.* You compare yourself only to government services, never to what people actually do.

**F. Fact corrections for your own documents.** 49 WAVs, not 46. `src/` is 2,089 lines. And the
README's 13.3%-cannot-read-Japanese statistic is doing work the product does not do — **your
interface is in English**, including both confirmation screens, so your actual user is an English
reader. Say that plainly.

---

## The Recommendation

**Split the product along the only three moments that actually exist, and be honest that the AI
currently sits in the wrong one.**

### 1 · BEFORE — registration (no panic, no clock, no second device)
The laptop app survives here, unchanged, doing what it already does: build a household's verified
Japanese audio bundle. This is the honest home of your Streamlit/OpenVINO stack. It is **not** where
the 6.97× applies, and you must not claim it is.

### 2 · DURING, uplink — the phone in the caller's hand
An offline PWA, ~4 MB, one home-screen icon. **One red button** that plays 救急です + address + room.
Three forced-choice vital buttons. A two-level symptom grid *after* dispatch. A permanent **STOP**.
**Zero AI at runtime — and you say that out loud, as a finding, not a confession.**

### 3 · DURING, downlink — the unbuilt half, and the reason the model exists
The dispatcher's Japanese, transcribed on-device and matched against a closed set of expected
dispatcher questions, shown to the caller in their language. No uplink injection. No physics wall.
One device. This is where Whisper and the classifier genuinely belong, and it is the strongest
honest thing you can put in front of a judge.

**The festival framing, and it is better than what you have now:**
> *We ablated our own model. We measured that the uplink carried five bits and did not need a 3B
> model to carry them — so we took it out and shipped the part that works on the phone people
> already hold. Then we measured where the model IS necessary: understanding the dispatcher. Here
> is the benchmark for both.*

A rigorously documented negative result is judgeable work. Concealing it is the only thing that
isn't. This also satisfies your own rule — the pitch follows the truth, rather than the truth being
shaped for the pitch.

**On the single-device verdict, bluntly:** injecting audio into a live call's uplink is impossible
on every platform. The *self-echo* loop — the phone playing its own audio out its own loudspeaker
into its own microphone on speakerphone — is **unproven, and your existing "PASSED" result does not
prove it**, because it was run over WhatsApp. It may work. If it does, everything above ships. If it
does not, the honest product is registration + downlink comprehension, and **you must be willing to
say that in writing before you run the test, so the result cannot be negotiated afterwards.**

### What to build and cut in seven days
| Day | Do |
|---|---|
| **Mon** | The corrected echo test (below). Write the raw result into `OPEN_DECISIONS.md` **before touching any code**, including the retraction of item 13's "PASSED". |
| **Tue–Wed** | The tap-only PWA: one red button, 3 vital buttons, 6 category tiles → terms, permanent STOP. Static HTML + `<audio>` over the 49 existing WAVs. |
| **Thu** | Install on a real phone. Five timed drills with your family: stopwatch **time-to-first-button** *and* **icon-find latency**. Both numbers go in the README. |
| **Fri** | Book and attend 普通救命講習 at our ward or Edogawa. Show it in the break. Write down verbatim what the firefighter says, good or bad. |
| **Sat** | Rewrite README and `OPEN_DECISIONS.md` to the truth. Delete the false claims listed below. |
| **Sun** | Buffer. Do not add features. |

**Cut, without negotiation:** the 7 untested languages, the map picker, 口頭指導/CPR content,
ontology expansion (D2), Japanese UI localisation, and any attempt to port models to a phone.

### The Nishikasai path — grounded, and slower than the Expansionist wants
The Indian International School in Japan and the Nishikasai community are the right target and you
are the right person to reach them. But **do not run a registration desk.** Ship the app so **each
family registers itself on its own phone** and the data never leaves it — that removes the APPI
problem, the consent problem, and the minor-as-data-controller problem in one design decision, and
it is a *better* architecture, not a compromise. Your metric is **installs with a completed
profile**, verified by a drill, not households processed. Ten real ones beat two hundred claimed.
Find one adult sponsor — a teacher, a parent, a Nishikasai clinic doctor — before you approach any
institution.

### Claims in the current README that are now false and must be deleted
1. **Line 80** — "The app runs on a device that stays in the building, already open, model already
   warm." Delete. This is the assumption you just killed.
2. **Line 335** — "The only real cost is a device that stays in the building." Delete.
3. **"Two devices, deliberately"** and the speakerphone choreography paragraph. Delete.
4. **The 3–6 minute on-scene delay claim as *your* target.** That clock starts when the crew
   arrives — after your window has closed. You may cite it as context; you may not claim to attack
   it.
5. **The 13.3%-cannot-read-Japanese statistic as justification.** Your UI is English. Keep the
   statistic only if you also state that limitation in the same paragraph.
6. **`OPEN_DECISIONS.md` item 13, "PASSED WITH ONE CAVEAT."** The caveat was the test. Downgrade to
   UNPROVEN until Monday's result.
7. **Total footprint "~3.9 GB per installed device."** After the split it is ~4 MB on the phone and
   3.9 GB on the registration machine. Two numbers, stated separately.

---

## The One Thing to Do First

**Tonight, run the corrected echo test — over a real cellular call, not WhatsApp — and write the
result into `OPEN_DECISIONS.md` before you write a line of code.**

Phone A places a **normal cellular call** to Phone B (not WhatsApp, not LINE, not FaceTime — those
are wideband Opus and are why your existing result is worthless). A on speakerphone, media volume
maximum. Play `data/audio/03f4fc3c57a080a2.wav` out of A's own loudspeaker. **Record what B
receives.** Repeat: A flat on a table, A held up, someone talking near A, and once with wired
earbuds in A. Repeat the entire set on the other OS — Apple and each Android OEM implement echo
cancellation differently, so one handset proves nothing.

Then play the recording to a Japanese speaker who has never heard the line and ask them to write
down the address. **If they cannot write 〇〇区〇〇四丁目12-3 101号室 from the recording, the
single-device uplink is dead** — and you will have learned it for the price of one phone call,
before building anything on top of it.

Decide now, in writing, what each outcome means. You do not get to decide after you see it.
