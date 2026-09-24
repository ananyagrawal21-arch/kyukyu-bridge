# Protocol — the messages between phone, server and console

Written 2026-09-19. **Design for review. Nothing here is built yet.**

This file defines the shape of every message that crosses between the caller's phone and the
dispatcher's console. It is deliberately written before any code, because the two ends have to
agree and because `ENGINEERING.md` section D says the instrumentation goes in from the first
commit, not after. Every decision below that costs something is marked with why.

---

## 0. The three rules this protocol has to obey

These come from `CLAUDE.md` and they constrain the field list more than anything else does.

1. **The model never generates Japanese that reaches a dispatcher.** So no message going to the
   console may contain a free-form Japanese string. Every Japanese word on that path is copied
   out of `data/ontology.json` (or, new, `data/questions.json`) and carries the id it came from,
   so the console can prove where it came from.
2. **English on screen, Japanese in the data.** So every item carries both: `ja` for the console,
   `en` for the caller's screen. Neither side ever has to read the other's language.
3. **The address is real.** Only one message type carries it. The event log never does.

---

## 1. The envelope — on every message, both directions

Every single message, no exceptions, starts with these fields. A message missing any of them is
dropped at the door and logged as `malformed`.

| field | example | what it is for |
|---|---|---|
| `schema_version` | `"1"` | so an old phone and a new server can tell they disagree |
| `session_id` | `"kb-20260919-7f3a92"` | one emergency call. Minted by the **phone**, see §7 |
| `msg_id` | `"m-014"` | unique inside the session; what an `ack` or `answer` points back at |
| `seq` | `14` | counts up per direction, no gaps. A gap means a message was lost |
| `direction` | `"phone_to_console"` | or `"console_to_phone"` |
| `type` | `"situation"` | picks which payload shape follows. Full list in §3 and §4 |
| `ts_device` | `"2026-09-19T18:42:07.311+09:00"` | the sending device's own clock |
| `ts_server` | `"2026-09-19T18:42:07.352+09:00"` | stamped **by the server on receipt**, never by the sender |
| `t_rel_ms` | `14310` | milliseconds since `t0`. This is the number the benchmarks use |
| `drill` | `false` | `true` = rehearsal. See §8 |
| `payload` | `{...}` | everything below |

**Why two timestamps.** The phone's clock and the console's clock are not the same clock, and on
a phone it can be seconds off. If we measure "dispatcher clicked → answer came back" using the
phone's clock at one end and the console's at the other, the number is garbage and we would never
know. So: each device records its own time for the record, the **server** stamps every message as
it passes through, and every published measurement uses `ts_server` only. `t_rel_ms` is the server
subtracting `t0` for you, because "14.3 seconds into the call" is the readable form.

**Why `seq` as well as `msg_id`.** `msg_id` says which message. `seq` says whether one went
missing. On a life-safety path, silently losing "she has stopped breathing" is the worst possible
failure, and without a gapless counter you cannot detect it.

**Why `drill` is in the envelope and not the payload.** A real console must be able to refuse a
test message without parsing it.

---

## 2. Session open and close

### `session.start` — phone → server, first message of every session

Carries the per-run config capture that `ENGINEERING.md` D4 asks for. Without this, two
measurements from two different builds are not comparable, and you cannot tell afterwards which
build produced which number.

| field | example |
|---|---|
| `t0` | `"2026-09-19T18:41:53.001+09:00"` — the zero point everything else counts from |
| `commit_hash` | `"d6be882"` |
| `app_version` | `"0.9.0"` |
| `ontology_version` | hash or date of `data/ontology.json` |
| `question_set_version` | hash or date of `data/questions.json` |
| `slm_model` / `slm_backend` | `"qwen2.5-3b-int4"` / `"OpenVINO GenAI + prefix caching"` |
| `stt_model` / `stt_backend` | `"whisper-small"` / `"openvino"` |
| `gates` | `{"negation": true, "lexical_veto": true}` |
| `discard_set` | the `SLM_DISCARD` membership for this run |
| `device` / `os` / `locale` | `"Pixel 7"` / `"Android 15"` / `"en-GB"` |

### `session.end`

| field | what it is for |
|---|---|
| `reason` | `completed` \| `caller_ended` \| `dispatcher_ended` \| `timeout` \| `crashed` |
| `duration_ms` | convenience; equals last `t_rel_ms` |

---

## 3. Phone → console

### 3.1 `profile` — the pre-registered details

Sent once, as early as possible — this is the message that beats the dispatch clock, because it
is ready before the caller has said a word.

| field | notes |
|---|---|
| `address` | `prefecture`, `city_ward`, `area`, `block_number`, `building`, `room`. Same keys as `data/profile.json`, so nothing is re-named on the way out |
| `address_confirmed` | `true` \| `false` \| `unknown`. **Not optional.** The caller may not be at the registered address, and a console must never render an unconfirmed address as fact |
| `patient` | `name`, `age`, `sex` (`male`\|`female`\|`unknown`), `sex_ja`, `known_conditions[]` |
| `patient_is_profiled` | `true` \| `false`. False means the call is about someone else, and the console must hide age/sex/conditions entirely rather than show the wrong person's |
| `caller` | `name`, `native_language`, `japanese_fluency` |
| `profile_updated_at` | FDMA requires 事前登録情報 be 「常に最新の状況であること」. The console should be able to see that a profile is two years stale |

`known_conditions[]` items are `{id, ja, en}` where `id` is a `conditions` entry from the
ontology. Free-typed conditions are allowed in the profile (a person may have something the
ontology does not list) but then `id` is `null` and the console shows it in a visibly separate
"not verified" block — same rule as unverified terms elsewhere.

### 3.2 `situation` — what we classified and the caller confirmed

The core clinical message.

| field | notes |
|---|---|
| `revision` | `1`, `2`, … The situation can change mid-call |
| `supersedes` | `msg_id` of the previous revision, or `null` |
| `items[]` | see below |

Each item in `items[]`:

| field | example | notes |
|---|---|---|
| `id` | `"not_breathing"` | the ontology id. **The proof of provenance** |
| `section` | `"symptom"` | `consciousness` \| `symptom` \| `event` |
| `ja` | `"息をしていません"` | copied verbatim from the ontology. Never generated |
| `en` | `"not breathing"` | for the caller's screen and for our logs |
| `frame` | `"observed"` | `observed` \| `reported`; the console phrases it accordingly |
| `aspect` | `"ongoing"` | `ongoing` \| `finished`, only for entries with a `finished` form |
| `critical` | `true` | lets the console sort without knowing our ontology |
| `verified` | `true` | the ontology's own flag, passed through |
| `source` | `"forced_question"` | `slm` \| `caller_added` \| `forced_question` \| `dispatcher_answer` |
| `confirmed` | `true` | did this pass through the caller's confirmation screen |

**Why `source` matters and is not optional.** It is the audit trail that says which findings came
from the model and which came from a human tapping a button. `RESPONSIBLE_AI.md` claims things
about that separation; this field is what makes the claim checkable from a log rather than from
my word. It also makes a new measurement possible for free: how often the caller deletes
something the model proposed.

**Items the caller removed do not go to the console.** They go in the event log as
`situation_item_removed`, because "the model said seizure and the human said no" is exactly the
data that tells us whether the classifier is trustworthy — but it is noise on a dispatch console
and could actively mislead.

### 3.3 `transcript` — the caller's raw words

| field | notes |
|---|---|
| `text` | as spoken, in the caller's language |
| `lang` | BCP-47. The language Whisper was forced to |
| `text_en` | English, when `lang` is not English |
| `is_final` | `false` for partials, `true` for the confirmed version |
| `corrected_by_caller` | whether the caller edited it on the confirm screen |
| `audio_ref` | an id, **not the audio**. Audio stays on the device unless `drill` is true |
| `asr_ms`, `audio_duration_ms` | the STT half of the dispatch clock |

**⚠️ This one needs your decision — see §9, question 1.** There is a real conflict between
"send the raw transcript" and the safety rule, and I have not resolved it on my own.

### 3.4 `answer` — a reply to a console question

| field | notes |
|---|---|
| `in_reply_to` | `msg_id` of the `question` |
| `question_id` | e.g. `"q_breathing_normal"` |
| `answer_id` | from that question's closed answer set — `yes` \| `no` \| `unknown` \| an enumerated id |
| `ja` / `en` | the pre-written pair for that `answer_id`. **Not generated, not translated** |
| `adds_situation_items[]` | ontology ids this answer implies, e.g. answering "no" to "is she breathing" adds `not_breathing` |
| `answer_latency_ms` | question displayed → answer sent. This is the round-trip number in `ENGINEERING.md` B |

### 3.5 `event` — every state transition

The instrumentation backbone. Small, frequent, never carries clinical content or PII.

| field | notes |
|---|---|
| `event` | name, from the closed list below |
| `phase` | the existing `app.py` phase name — `dispatch_now`, `recording`, `confirm_transcript`, `confirm_symptoms`, `ask_awake`, `ask_breathing`, `ask_circulation`, `ask_patient`, `briefing`, `handoff`. **Reused exactly, not re-invented**, so a log line matches a screen you can point at |
| `detail` | a small flat dict. Ids and numbers only |

Event names, v1: `app_opened`, `dispatch_pressed`, `call_dialing`, `call_connected`,
`recording_started`, `recording_stopped`, `asr_done`, `classify_done`, `phase_entered`,
`phase_left`, `back_pressed`, `situation_item_added`, `situation_item_removed`,
`briefing_chunk_played`, `question_displayed`, `guide_started`, `guide_step_advanced`,
`first_compression_prompt`, `handoff_shown`.

Those names are chosen so that every row in `ENGINEERING.md` section B becomes a subtraction
between two events, and nothing else has to be built to measure it:

- app open → 119 dialling = `app_opened` → `call_dialing`
- "stop speaking" → data on console = `recording_stopped` → the console's `ack` of `situation`
- dispatcher clicks → answer back = `question` `ts_server` → `answer` `ts_server`
- call connect → first compression = `call_connected` → `first_compression_prompt`

### 3.6 `ack` — phone → console and console → phone

| field | notes |
|---|---|
| `in_reply_to` | the `msg_id` being acknowledged |
| `status` | `received` \| `displayed` \| `dismissed` \| `failed` |
| `error` | free text, our own logs only, when `failed` |

**`displayed` is separate from `received` on purpose.** The dispatcher needs to know the caller
actually *saw* the question, not merely that a server accepted it. It is also the honest end of
the round-trip measurement: a stopwatch that stops when the packet lands flatters us.

---

## 4. Console → phone

### 4.1 `question` — from the closed protocol set

| field | notes |
|---|---|
| `question_id` | `"q_breathing_normal"` |
| `ja` | the wording on the dispatcher's own screen |
| `en` | the pre-written English the caller sees |
| `answers[]` | `{answer_id, en, ja}` — the closed set of allowed replies |
| `priority` | `normal` \| `interrupt`. `interrupt` takes over the caller's screen |
| `requires_ack` | `true` for anything clinical |

**The English is written in advance and human-verified, exactly like the ontology.** It lives in
a new `data/questions.json` with the same `verified: true` discipline, and the same rule that
nothing ships unverified. This is the ontology property pointed the other way: on the outbound
path a closed set stops the model inventing Japanese; on the inbound path it stops the model
inventing English *about a medical instruction*, which is the same risk with the languages
swapped. No runtime translation is involved in either direction.

### 4.2 `free_text` — the dispatcher typed something the set does not cover

| field | notes |
|---|---|
| `text_ja` | what the dispatcher typed |
| `text_en` | machine translation, for the caller |
| `translation_engine` | which engine, recorded per message |
| `is_machine_translated` | always `true`, and the caller's screen always says so visibly |
| `reply_mode` | `closed_only` — see below |

**This message cannot round-trip as free text.** The caller's reply to it is restricted to the
closed answer set (`understood`, `not_understood`, `yes`, `no`, `unknown`). If the caller could
type back and we translated it, the model would be generating Japanese onto a dispatcher's
console — the one thing the project says it never does. `reply_mode` is in the message so that
rule is enforced by the protocol rather than by remembering.

Counting these messages answers an `ENGINEERING.md` B question directly: **how often does the
dispatcher need free text at all?** If the answer is "almost never", the translation lane is not
worth building, and we will have measured that instead of guessed it.

### 4.3 `command` — the dispatcher drives the caller's screen

| field | notes |
|---|---|
| `command_id` | closed set, below |
| `params` | e.g. `{"rate_bpm": 110}` |
| `requires_ack` | `true` for all of the guides |

Command ids, v1: `start_cpr_guide`, `stop_cpr_guide`, `start_choking_guide`,
`start_bleeding_guide`, `show_unlock_door`, `show_meet_crew_outside`, `hold_and_listen`,
`end_session`.

**The CPR guide has two trigger paths, not one.** `OPEN_DECISIONS.md` settled that CPR guidance
must not wait on inbound capability — the app already asked whether the patient is breathing, so
it can offer the guide with no console at all. So the guide records `trigger_source`:
`dispatcher` \| `app_rule` \| `caller`. The dispatcher command *refines* the timing; it is not a
prerequisite. That field also lets us measure which trigger actually gets to first compression
faster, which is the number in `ENGINEERING.md` E worth more than any F1 point.

---

## 5. What never crosses

- No Japanese string anywhere that does not have an `id` pointing into a verified data file.
- No free text from the phone to the console, in any language, in any message type.
- No audio to the console. `audio_ref` is an id; the file stays on the device.
- No address in any `event`. Events carry ids and numbers.

---

## 6. The log, and the address

One JSON-lines file per session, every message exactly as it crossed, in `ts_server` order.
That file **is** the replay harness input (`ENGINEERING.md` D2) — no separate format.

- `data/sessions/` goes in `.gitignore` before the first session is ever written, for the same
  reason `data/profile.json` is there.
- The `profile` message is the only one that ever contains the address. In a log kept for
  measurement, the `profile` payload is replaced by `{"profile_hash": "<sha256 prefix>"}` —
  enough to prove two runs used the same profile, not enough to be an address.
- Replay fixtures and anything committed use `data/profile.example.json`.

---

## 7. Who mints the session id

**The phone, at the moment the caller presses the dispatch button** — before the server or the
console knows anything exists.

Because the first thing `ENGINEERING.md` B wants measured is *app open → 119 dialling*, and that
whole interval happens before any network round-trip. If the server minted the id, the session
could not have a `t0` until the network answered, and the measurement we most want would start
too late. It also means the app works, and logs, with the server unreachable.

Format: `kb-<YYYYMMDD>-<6 random hex>`. No device id, no phone number, nothing derived from the
person.

---

## 8. Drill mode

`drill: true` in the envelope, set once at `session.start` and never changed mid-session.
A drill session is identical in every other respect — same messages, same fields, same log.

This is `ENGINEERING.md` D3: the rehearsal the user needs and the measurement rig we need are the
same thing. If drill mode took a different code path, it would stop being evidence about the real
one.

---

## 9. Open questions — I did not decide these for you

**1. Does the raw transcript go to the console at all?**
This is the real conflict in the design. The transcript is in the caller's language, so a Japanese
dispatcher cannot read it; machine-translating it would put model-generated Japanese on a
dispatcher's console, which the project's core safety property forbids. Three options:
 (a) don't send it — the ontology items are the clinical content and the transcript adds nothing
 the dispatcher can use; (b) send it, display it small and clearly marked as the caller's own
 untranslated words — provenance, not content, the way a scan is attached to a report;
 (c) send a translation, which I think you should reject.
**My recommendation: (b).** It costs nothing, it keeps the safety property intact because nobody
is asked to act on it, and a dispatcher who can see *something* was said is less likely to think
the line is dead. But it is your call and it touches the claim in `RESPONSIBLE_AI.md`, so it
should be your decision and not a default I picked.

**2. Full `situation` re-send, or deltas?**
I have written it as a full re-send with `revision` and `supersedes`. It is more bytes and much
harder to get wrong — a lost delta leaves the console silently showing a stale picture, and on
this path silent staleness is the dangerous failure. Recommend keeping full re-send unless the
link turns out to be too slow for it, which we can measure rather than assume.

**3. Does `question` need a timeout?**
A question the caller never answers sits on the dispatcher's screen forever. I have not added
`expires_at` because I do not know what a dispatcher expects to see when it lapses, and guessing
at dispatcher workflow is exactly the kind of thing the 消防本部 conversation in
`ENGINEERING.md` C would settle in five minutes.

**4. Is `known_conditions` free text allowed at all?**
I allowed it with `id: null` and a visibly separate block. The alternative is to force every
condition into the ontology's 27 entries, which would be cleaner but would silently drop a real
person's real diagnosis. Flagging because it is the one place I let unverified text through.

---

## 10. What this is not

No transport, no auth, no encryption, no retry policy, no framing. Those are real and they are
deliberately out of scope here — this file is the *shape of what is said*, so it can be reviewed
before anything is built. The 専用端末 at the fire HQ and the 標準インターフェイス hop beyond it
have their own constraints, and none of them change the field names above.
