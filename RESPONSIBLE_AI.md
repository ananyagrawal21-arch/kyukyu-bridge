# Responsible AI, Privacy and Safety

*Kyūkyū-Bridge (救急ブリッジ)*

This system speaks on someone's behalf during a medical emergency. A wrong sentence is not a bad
user experience — it can send an ambulance to the wrong building or tell a dispatcher that a
breathing patient has stopped breathing. Every design decision below follows from that.

---

## 1. Safety: the architecture, not a filter

The central safety property is structural rather than a guardrail bolted on afterwards:

> **No generative model ever produces Japanese that reaches a live emergency call.**

Every Japanese sentence the application can say is either a fixed template or one of 31
ontology terms verified in advance by a fluent Japanese speaker, and all of them are rendered to
audio *before* the app runs. The language model's only job is to **select which pre-verified
terms apply** to what the caller said. It cannot invent a symptom name, mistranslate a street, or
hallucinate a sentence, because it is never in the business of writing Japanese at all.

This is why the ontology is closed. A closed set is what makes the guarantee checkable.

### Three further safety mechanisms

**Critical binary facts are taken from a human, never inferred.** Consciousness, breathing and
circulation are excluded from model classification entirely (`SLM_DISCARD`) and come from
forced-choice buttons the caller answers. These are the fields where an inversion is lethal, so
the model is not permitted an opinion on them.

*This was not theoretical caution.* During non-English testing, Whisper's translate mode inverted
"there is no response" into its opposite in **both** languages tested. The corruption never
reached the briefing — precisely because consciousness comes from a button. The architecture
caught a failure it was designed for, arriving by a route nobody anticipated.

**Anti-fabrication verification.** Classification runs in two stages: candidate generation, then
a per-candidate review pass that rejects anything unsupported by the caller's actual words.
Measured effect: **precision 1.00, zero fabrications on clean English** across a 52-case set.

**Omit rather than guess.** Where a fact is unconfirmed, the briefing says nothing rather than
saying something plausible. Applied to patient identity, unknown sex, unmatched symptoms and
location. A dispatcher asking a follow-up question costs seconds; a confident wrong answer costs
more. An entire "not at this registered address" feature was **deleted** rather than shipped with
wording that carried no real information.

**The human confirms twice.** The caller sees the transcript before it is used, and sees the
understood symptoms before they are spoken — able to remove a wrong one and add a missed one.

---

## 2. Honest limits, measured rather than claimed

Stating these is part of responsible deployment, not a disclaimer.

| Claim | Measured reality |
|---|---|
| Zero fabrications | True for **clean English**. Under simulated panic (repetition, false starts, filler): precision falls to 0.96, F1 0.98, **2 fabrications in 52 cases**. |
| Multilingual | 2 of 9 offered languages verified end-to-end. Whisper is weakest on some languages — **Nepali, Burmese** — whose speakers are among the most vulnerable. We do not claim uniform coverage. |
| Panic robustness | Tested by perturbing **text**. Real panic also degrades audio before transcription, so this is a lower bound. |
| Elderly users | An elderly person living alone who is both patient and caller is served **poorly** by this app. They are better served by Japan's existing 三者間同時通訳 service, which needs no device. |
| Deployment | Working prototype. Not deployed at scale, and no paramedic or dispatcher has yet reviewed it. |

**Known open defect, disclosed:** translate-mode negation inversion (above) is contained for
consciousness but could in principle affect a non-excluded symptom. The confirmation screen is
the remaining backstop, and its labels are currently English — weakest for exactly the callers
most exposed to this bug. Interface localisation is the fix and is prioritised.

---

## 3. Privacy and data handling

**No user data leaves the device, ever.** There is no account, no telemetry, no cloud inference
and no analytics. Speech recognition and classification both run locally.

**Network access is confined to setup.** Address lookups (postal code, national map data,
OpenStreetMap) happen once, while registering an address. **During an emergency there is no
network call of any kind** — no map, no GPS, no API. The app works with the internet unplugged.

**What is stored, and where:**

| Data | Location | Protection |
|---|---|---|
| Address, patient age/conditions, names | `data/profile.json` | Git-ignored — never committed |
| The same details **spoken aloud** as audio | `data/audio/profile/` | Git-ignored, `chmod 0600` (owner-only) |
| Shared non-personal phrases | `data/audio/` | Committed; contains no personal data |

The audio split is a deliberate privacy boundary. Pre-rendered speech files say a real home
address out loud; excluding the text while committing the audio would have leaked exactly what
excluding the text was meant to prevent. Default file permissions let every account on the
machine read them, so they are explicitly locked to the owner.

**Deletion is automatic, not manual.** When a profile changes, audio for the previous address or
previous medical conditions is **deleted from disk**, not merely orphaned. Without this the
folder would slowly accumulate a spoken history of every address and condition ever entered.

**No biometrics.** No facial data, no camera, no voiceprint, no speaker identification. Audio is
transcribed in memory and never written to disk.

**Data provenance.** Nothing is scraped and no user data trains anything. The ontology derives
from Japan's official dispatcher protocol (緊急度判定プロトコル Ver.1, FDMA) and was
human-verified. Address data comes from Japan Post, 国土地理院 and OpenStreetMap.

---

## 4. Bias and fairness

**The known bias is in speech recognition, and it runs the wrong way.** Whisper's accuracy varies
by language and accent, and it is weaker on several languages whose speakers have the least
access to alternatives. We tested accented English against the L2-ARCTIC corpus and disfluent
panicked speech against a purpose-built set, and we publish both results rather than a headline.

**Mitigations:** the caller's language is set from their profile rather than auto-detected,
removing a whole class of wrong-guess failures; a one-tap switch handles callers more comfortable
in a different language; and the confirmation loop means a transcription error is *caught* rather
than acted on.

**Design bias we chose deliberately.** The system asks the human whenever the answer matters
clinically and the model cannot know it. That is slower. It is also the difference between an
error the caller can correct and one they never see.

---

## 5. Environmental cost

Inference is on-device on hardware the household already owns — a 3B model quantised to INT8 and
a small speech model. **No datacentre GPU is invoked for any emergency call**, and nothing is
trained by us. Marginal energy per call is that of a few seconds of laptop CPU.

---

## 6. GenAI-specific risks

| Risk | How it is addressed |
|---|---|
| **Hallucinated content** | The model selects from a closed list. It cannot emit a term that does not exist. |
| **Fabricated symptoms** | Second-stage per-candidate verification. Measured precision 1.00 on clean English; 0.96 under panic, disclosed above. |
| **Confident wrong answers** | Omit-rather-than-guess, plus two human confirmation steps. |
| **Automation bias** (trusting the machine over your own eyes) | The app never auto-plays. The caller presses each button, having seen what it will say. |
| **Silent model drift** | Every spoken sentence is pre-rendered from verified text; changed wording misses the content-hash cache and is re-rendered, so stale audio cannot outlive the text it belongs to. |
| **Scope overreach** | The system assists during the opening minute of a call. It does not diagnose, does not triage, and does not replace the dispatcher. |

---

## 7. Transparency

`OPEN_DECISIONS.md` is a complete engineering log — decisions, measurements, rejected
alternatives, and the bugs we shipped and then fixed, with dates. It is deliberately not a
highlight reel. `DISCLOSURE.md` records which generative-AI tools were used in development and
for what.
