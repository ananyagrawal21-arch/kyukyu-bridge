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
Koto and Edogawa fire stations run free, publicly-enrollable 普通救命講習 — three hours in a room
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
reviewer confirmed it: **a caller who cannot read Japanese cannot pronounce 江東区南砂.** Romaji
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
| **Fri** | Book and attend 普通救命講習 at Koto or Edogawa. Show it in the break. Write down verbatim what the firefighter says, good or bad. |
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
down the address. **If they cannot write 江東区南砂四丁目24-5 405号室 from the recording, the
single-device uplink is dead** — and you will have learned it for the price of one phone call,
before building anything on top of it.

Decide now, in writing, what each outcome means. You do not get to decide after you see it.
