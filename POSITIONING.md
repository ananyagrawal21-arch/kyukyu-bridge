# Positioning — competitions, and the pathway that replaced the two-device problem

Written 2026-09-19. This file is the argument, not the code. It records WHY the project is
defensible, so the reasoning survives the next time the design is questioned.

---

## 1. The pivot that made everything else possible

For three weeks the project was blocked on one thing: the app had to speak Japanese into a live
119 call, and on Android that is impossible. Verified at source level:

- `AudioManager.getCallUplinkInjectionAudioTrack()` exists but needs `CALL_AUDIO_INTERCEPTION`,
  declared `signature|privileged|role`. The only role that grants it is `SYSTEM_CALL_STREAMING`,
  `systemOnly="true"` with a ROM-config default holder. Unreachable by a Play Store app.
- `CallRedirectionService` cannot touch emergency calls — Telecom disconnects the call.
- Emergency calls always use the preloaded dialer, even if a third-party app holds `ROLE_DIALER`.
- 050/VoIP cannot dial 119 in Japan (location transmission requirement, 総務省).
- The acoustic path (loudspeaker → own mic) is per-chipset and fails SILENTLY — the user hears
  the audio perfectly while the dispatcher gets nothing. Disqualifying for a life-safety product.

On iOS `AVSpeechSynthesizer.mixToTelephonyUplink` works (shipped since iOS 13, used by AAC apps
such as Proloquo4Text). But a single product cannot be built on a capability half the handsets
lack, and the target population likely skews Android.

**The resolution was not a workaround. The requirement was wrong.** Nothing about helping this
person requires the sound to come from the machine. The information has to reach the dispatcher;
it does not have to reach their ear.

## 2. The pathway

**「消防機関への緊急通報に係る標準インターフェイス」** — FDMA's standard interface between fire
dispatch systems and external emergency-reporting services.

- Architecture (revised Feb 2024): your service → a 専用端末 you install at the fire HQ →
  標準インターフェイス → 指令台. Only the last hop is standardised.
- Deliberately leaves your own protocol free: 「通信方式を規定しないことで緊急通報サービス側の
  自由度、サービスの拡張性を確保」
- Carries: 画面転送（RDP等）, structured data (JSON), images ≤20MB, video ≤512MB.
- **Bidirectional.** 「消防指令システムから緊急通報サービス側へのデータの送信も可能な仕様とした」
- Eligibility: 「不特定多数の利用者を対象としたものではなく…又は事前登録制のサービスであるなど、
  利用者が限定されていること」 — Kyūkyū-Bridge is a pre-registration service. Qualifies.
- Nothing requires a disability, a nationality, a telecom licence, or a certification body.
- Requirements assume a service like this: 「事前登録の情報（通報者名、住所情報等）は常に最新の
  状況であること」
- Timing: standard spec published Oct 2023 / Mar 2024. Dispatch systems replace at peak
  FY2024–2026. The window is open now.

Precedents, both private companies: NET119 (Dawn Corp, pre-registration, sold as a cloud service
to fire departments) and HELPNET (operator relay, connected to all 720 fire departments).

**Open architectural question:** 「通話による通報は今回のインターフェイス対象外」 — voice-call
reporting is out of scope for the interface. Unresolved whether the service reports *alongside*
a voice call or *instead of* one. This replaced the two-device problem as the live design question.

## 3. Why this is strong for competitions specifically

Recorded verbatim because these are the arguments to elaborate later.

**Judges ask "why hasn't someone already done this?" Most entries can't answer. This one can,
with citations.** Android blocks call audio at source level; iOS allows it via one accessibility
API; 119 cannot be dialled over VoIP by law; NET119 is disability-gated; and dispatchers
themselves asked FDMA for multilingual translation and nobody built it. That depth of *why the
whitespace exists* is what separates a project from a demo.

**Measurements, not claims.** A 95-case evaluation harness, precision/recall/F1 reported
separately for Stage A and Stage A+B, and a dedicated cardiac-arrest false-positive gate that
fails a run on its own. Most entries have a demo and a slide saying "94% accurate."

**Negative results, which almost nobody reports.** Three attempts to make the verifier stricter
all made it worse (36→34, 36→24, and a 2026-08-03 inversion that dropped F1 0.91→0.77).
Completing the missing glosses dropped the probe 36→33 and produced a CPA false positive.
Reported rather than hidden. Engineers on a judging panel recognise this instantly.

**A regulatory pathway found by reading primary sources.** FDMA working-group minutes, a standard
interface that opened in 2024, and an eligibility clause the architecture satisfies. Unlikely any
other student entry in Japan has done this.

**A government-validated problem.** 23.9% of foreign residents converse freely in Japanese;
13.3% can barely or not at all read it; 4M+ foreign residents; 9.8 min mean ambulance response;
bystander CPR takes 1-month neurologically-intact survival from 3.7% to 10.4% (令和7年版
救急・救助の現況).

**Positioning:** applied research with a deployment pathway, NOT a startup. Judges detect an
invented business model instantly; they cannot fake-detect a working system with measurements
behind it. Lead with *"a foreigner and a Japanese dispatcher have a conversation, and neither
speaks the other's language."* The AI is how, not what.

**The three questions judges will ask:**
1. *Does this work?* — needs the live two-way demo. Currently the gap.
2. *Why you?* — lives in the affected community, speaks the language, found the pathway,
   a year of measured work. Genuine answer.
3. *What's the path to users?* — weakest point. One conversation with a fire department,
   even "we'd be interested," changes this answer completely.

## 4. Honest gaps

- No working two-way demo yet.
- No contact with any fire department.
- Not one household has this installed.
- The ablation is measured but not written up.
- Cannot sign contracts, hold liability insurance, or be an APPI data controller at 17.
  A business needs an adult co-founder. Competitions do not.

## 5. What was deleted, and why it wasn't a loss

Only the pre-rendered Japanese WAVs played into the call — file playback, never a model. Whisper,
the classifier, the negation gate, the evidence veto, CPA promotion and the OpenVINO work are all
untouched. TTS returns pointed the other way: spoken to the CALLER, in their language, because a
person doing chest compressions cannot read a screen.

The system went from one-way to two-way. That is more work, not less.

## 6. Where Kyūkyū-Bridge sits — reference services (logged 2026-09-26)

Kept on purpose, to be re-evaluated from time to time. These services are **references, not role
models** — they validate pieces of the mechanism, they do not decide our design.

**Smart911 (USA) is the main reference.** It is the closest existing service to what we are
building: a citizen pre-registers a profile (address, household, medical conditions, disabilities,
primary language); when that phone number calls 911, the profile appears on the call-taker's
screen automatically; the voice call carries on as normal. It shows the dispatcher the caller's
language — and stops there. Nothing bridges the conversation.

| | Smart911 | Apple Medical ID + RapidSOS | Prepared / Carbyne | **Kyūkyū-Bridge** |
|---|---|---|---|---|
| Pre-registered profile | ✅ | ✅ | ❌ | ✅ |
| Voice call continues | ✅ | ✅ | ✅ | ✅ |
| Data on dispatcher's screen | ✅ | ✅ | ✅ | ✅ |
| Shows the caller's language | ✅ | ❌ | ✅ | ✅ |
| **Actually bridges the language** | ❌ | ❌ | ✅ | ✅ |
| **Closed, verified output (no open machine translation)** | — | — | ❌ | ✅ |
| **Guides the caller in their own language** | ❌ | ❌ | partly | ✅ |

**The one-sentence version:** Smart911 is validated in 3,500+ US municipalities. It already shows
the dispatcher the caller's language — and then stops. Kyūkyū-Bridge is the part that comes after:
actually bridging that language, with output a human verified in advance.

Every row except the last three is proven at scale elsewhere. The last three are what we add.
Prepared and Carbyne bridge language with **open** machine translation — exactly what FDMA said it
doubted in 2017 (「その精度に疑問が残る」). The closed ontology is the answer to that objection.

**The warning that comes with the reference:** Smart911 in Arkansas — statewide since 2013,
$825,000 a year — had ~22,000 household profiles about three years in, under 2% of households
(Fox16 investigation). Citizen registration is the known weak point of this whole family.

What each reference validates:

| Service | Country | Validates |
|---|---|---|
| Smart911 (Motorola Solutions) | USA | pre-registered profile → screen, by phone number, alongside the call |
| Apple Medical ID via RapidSOS | USA, Canada | pre-registered data sent automatically on call; no separate sign-up |
| nora | Germany | pre-registered medical data stored on the phone, sent only in an emergency |
| PEMEA (ETSI TS 103 478) | Europe | "caller language" as a standard field sent to emergency centres |
| AML | EU, UK, 30+ countries | data travelling alongside a voice call, at national scale |
| Live119 | Japan | data on the console while the call continues; used for 口頭指導 |
| Prepared, Carbyne | USA | emergency agencies pay for AI translation |

Sources: smart911.com FAQ pages (Cortland County, Prince William County); Fox16 "Is Smart911
Helpline in Need of Lifeline?"; rapidsos.com; support.apple.com/en-us/105072; nora-notruf.de FAQ;
eena.org PEMEA and AML pages; dawn-corp.co.jp/service/live119; prepared911.com; Axon investor
release 2025-09-23; carbyne.com.

### 2026-09-26 update to section 2's open question — read from the primary source

FDMA's 「消防機関が緊急通報サービスに求める条件」(第1版, 令和6年3月) settles most of it:

- The voice exclusion reads 「データ通信による音声通話は標準インターフェイスでは行わない」 — the
  interface does not **carry** voice over data. It does not forbid a service being used while an
  ordinary 119 phone call continues. Live119 already runs that way at 80+ departments.
- Eligibility is 「事前登録制のサービスであるなど、利用者が限定されていること」 — registration
  with the **service**. Nothing requires each user to register with a fire department.
- The 専用端末 must have its own display and work **on its own** if the link to the 指令システム
  fails. So a terminal with no 指令台 integration is the spec's own fallback mode.
- The service must meet: APPI and local-government security guidelines; encryption in transit and
  at rest (CRYPTREC list); fixed server IPs; logs kept ≥1 year; intrusion detection; malware
  protection; incident notification. Conformance is presented by the service to each department;
  no certification body.
