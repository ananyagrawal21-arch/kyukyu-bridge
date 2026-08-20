"""Kyūkyū-Bridge - one-button emergency UI (Streamlit).

REAL-WORLD USE: any INDOOR PLACE WITH A FIXED, REGISTERED ADDRESS keeps this OPEN and running
on a device that stays there (hence warm_brain() below - the model loads at app-open, never
mid-emergency). A home is the obvious case, but nothing here is home-specific: a company
dormitory, a care facility, a language school and a share house all work identically, because
the only requirement is that the address in profile.json is the address of the building the
device is sitting in.

When someone collapses, the caller dials 119 on their PHONE and puts it on SPEAKERPHONE, then
works this app on the fixed device, holding the phone toward its speaker. Two devices is not a
Streamlit limitation: a phone cannot inject app audio into a live call, and its echo
cancellation would suppress it if you tried.

WHY INDOORS IS THE RIGHT SCOPE, not a retreat: Japan already solves the outdoor/mobile case
better than we could. Mobile 119 calls transmit the caller's location automatically
(緊急通報位置通知, carrier-level, nationwide), and 三者間同時通訳 patches a live human
interpreter into any call from any phone (673/720 fire departments, 93.5%, Jan 2025). What
NEITHER can supply is the room number and the patient's medical history - which is exactly
what a registered indoor address plus a stored profile give you.

Flow: 119 dialled FIRST -> EMERGENCY -> [dispatch_now: play 救急です + address IMMEDIATELY,
this is what sends the ambulance] -> speak/upload -> Whisper -> confirm transcript ->
SLM brain -> confirm understood symptoms -> awake/breathing/circulation -> patient ->
remaining briefing chunks, delivered while the ambulance is already en route.
"""
import os
import re
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Use the fast INT8 OpenVINO brain if it's been converted.
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "qwen2.5-3b-ov-int8")
if os.path.isdir(_MODEL_DIR):
    os.environ.setdefault("SLM_OV_DIR", _MODEL_DIR)

from pipeline import (  # noqa: E402
    build_briefing_chunks, slm_matches, _statement_from, _humanize,
)
from briefing_template import render_location_pieces, HANDOFF_LABELS  # noqa: E402
from pipeline import build_handoff  # noqa: E402
from slm_classify import SLM_DISCARD  # noqa: E402
from ontology import load_ontology  # noqa: E402
from caller_profile import load_profile, romaji_fields  # noqa: E402
from postal import lookup as postal_lookup, looks_romaji  # noqa: E402

st.set_page_config(page_title="Kyūkyū-Bridge", layout="centered")

st.markdown(
    """
    <style>
      #MainMenu, header, footer {visibility: hidden;}
      .stApp {background: #0f0f0f;}
      .block-container {max-width: 680px; margin-left: auto; margin-right: auto;}
      /* Hide Streamlit's own "learn how to enable microphone access" link - it points at
         Streamlit's docs and breaks the app's identity. Only shows pre-permission anyway. */
      [data-testid="stAudioInput"] a {display: none !important;}
      /* Secondary buttons stay small and subdued - only the emergency button is huge. */
      div.stButton > button {font-size: 1.05rem; border-radius: 12px;}
      .caption {text-align: center; color: #bbb; font-size: 1.1rem; margin: 1vh 0 2vh;}
      .status {text-align: center; color: #fff; font-size: 1.7rem; font-weight: 700; margin: 3vh 0 1vh;}
      .transcript {text-align: center; color: #fff; font-size: 1.4rem; background: #1c1c1c;
                   padding: 1.2rem; border-radius: 16px;}
      .briefing-jp {color: #fff; font-size: 1.6rem; line-height: 2.4rem; background: #10221a;
                    border: 1px solid #1f6f4a; padding: 1.4rem; border-radius: 16px;}
      /* The element container sits in a flex column that shrinks children to content width,
         so the button's width:100% resolved against ~150px. Force the chain to full width. */
      div.st-key-emergency, div.st-key-emergency > div.stButton {
        width: 100% !important; text-align: center;
      }
      div.st-key-emergency button {
        background: #d32f2f; color: #fff; font-size: 2.3rem !important; font-weight: 800;
        letter-spacing: 0.05em; width: 400px; max-width: 90%; height: 230px;
        border-radius: 24px !important; border: none;
        box-shadow: 0 8px 32px rgba(211,47,47,0.4); margin-top: 6vh;
      }
      .st-key-emergency button:hover {background: #b71c1c; color: #fff;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_data():
    """Profile is None on a machine that has not been set up yet - the app sends you to the
    setup screen instead of crashing."""
    try:
        profile = load_profile()
    except (FileNotFoundError, ValueError):
        profile = None
    return profile, load_ontology()


@st.cache_data(show_spinner=False)
def speak(jp_text: str):
    """Japanese audio for a briefing chunk, cached so it renders once per chunk."""
    from speak import speak_japanese
    return speak_japanese(jp_text)


# Common languages a caller might switch to if their profile default is wrong (e.g. more
# comfortable in English than their registered language, mixed-language household).
LANGUAGE_OPTIONS = {
    "en": "English", "vi": "Tiếng Việt", "zh": "中文", "ko": "한국어",
    "tl": "Tagalog", "th": "ไทย", "pt": "Português", "ne": "नेपाली", "id": "Bahasa Indonesia",
}


def transcribe(file_like, language: str, task: str = "transcribe"):
    """Delegates to src/stt.py so the app and CLI share one implementation.

    Reads the clip into memory first: for a non-English caller we run Whisper TWICE over the
    same audio, and a file-like object is exhausted after the first read.
    """
    import io
    from stt import transcribe as _transcribe

    data = file_like.read() if hasattr(file_like, "read") else None
    src = io.BytesIO(data) if data is not None else file_like
    return _transcribe(src, language=language, task=task)


def go(phase):
    st.session_state.setdefault("history", []).append(st.session_state.phase)
    st.session_state.phase = phase
    st.rerun()


def back():
    hist = st.session_state.get("history", [])
    if hist:
        # Leaving the briefing means an earlier answer may change, so the composed chunks are
        # stale. Drop them; the briefing phase rebuilds on entry. Without this, going back to
        # fix "is it this person?" would return you to the OLD briefing.
        if st.session_state.phase == "briefing":
            st.session_state.pop("chunks", None)
            st.session_state.pop("chunk_i", None)
        st.session_state.phase = hist.pop()
        st.rerun()


# Screens that get the generic "previous step" button. Deliberately NOT every screen:
#   idle                - it IS the start; there is nothing behind it.
#   confirm_transcript  - already has "Say it again", which is the same move but clearer.
#                         A generic back would also land on `recording` with the clip still
#                         loaded, which re-transcribes immediately and looks like nothing
#                         happened.
# `briefing` DOES get one: it has its own back, but that only walks the chunks, so from the
# final screen there was no way back to an earlier question at all. The two are disambiguated
# by name - "Previous part" moves within the briefing, "Previous step" leaves it.
BACKABLE = {"dispatch_now", "recording", "confirm_symptoms", "ask_awake", "ask_breathing",
            "ask_circulation", "ask_patient", "briefing"}


# The flow in order. A panicking caller needs to see the end coming - an unbounded sequence of
# screens feels endless, which is its own source of panic. Breathing and circulation are skipped
# when the caller already mentioned them, so the total is computed per-call rather than fixed.
FLOW_STEPS = [
    "dispatch_now", "recording", "confirm_transcript", "confirm_symptoms",
    "ask_awake", "ask_breathing", "ask_circulation", "ask_patient", "briefing",
]


def show_progress(phase):
    skip = set()
    if not st.session_state.get("need_breathing", True):
        skip.add("ask_breathing")
    if not st.session_state.get("need_circulation", True):
        skip.add("ask_circulation")
    steps = [s for s in FLOW_STEPS if s not in skip]
    if phase not in steps:
        return
    i, total = steps.index(phase) + 1, len(steps)
    st.markdown("<br>", unsafe_allow_html=True)
    if phase in BACKABLE and st.session_state.get("history"):
        if st.button("← Previous step", key=f"back_{phase}"):
            back()
    st.progress(i / total)
    st.markdown(f'<div class="caption">Step {i} of {total}</div>', unsafe_allow_html=True)


def reset():
    for k in ("phase", "transcript", "entries", "extras", "need_breathing", "history",
              "need_circulation", "at_registered_address", "patient_ok", "chunks", "chunk_i", "stt_language",
              "transcript_en"):
        st.session_state.pop(k, None)
    # The per-symptom aspect radios are keyed by symptom id, so they are not in the list above.
    # Left behind, a previous call's "Has stopped" would silently pre-select on the next one.
    for k in [k for k in st.session_state if k.startswith("aspect_")]:
        st.session_state.pop(k, None)
    st.session_state.phase = "idle"
    st.rerun()


profile, ontology = get_data()


@st.cache_resource(show_spinner="Preparing the emergency assistant… (loads once at startup; stays ready while open)")
def warm_brain():
    """Load + compile the brain when the app OPENS, not during an emergency. Cached, so it
    runs once per server session; the on-disk compile cache makes even that fast after the
    first-ever launch."""
    from slm_classify import classify
    classify("warming up", ontology)
    return True


warm_brain()  # ready before the user ever taps EMERGENCY

if "phase" not in st.session_state:
    st.session_state.phase = "idle"
phase = st.session_state.phase


# ---- 0. SETUP: fill this in once, long before it is needed. ----
# Was a terminal script (tools/setup_profile.py, still there for headless use). A family
# setting this up will not open a terminal, and the details MUST be entered before an
# emergency - there is no time to type an address while someone is on the floor.
if profile is None and phase != "setup":
    st.session_state.phase = phase = "setup"

if phase == "setup":
    p = profile or {}
    addr, pat, cal = p.get("address", {}), p.get("patient", {}), p.get("caller", {})

    st.markdown('<div class="status">Your details</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="caption">Fill this in once, now. In an emergency the app says it for '
        'you — there is no time to type. It stays on this device.</div>',
        unsafe_allow_html=True,
    )

    # POSTAL CODE FIRST, and outside the form - a non-submit button inside an st.form does
    # nothing until submit, and this has to work on its own. Placed at the top because it is
    # the step that saves the user from the impossible task: typing their own address in
    # Japanese when they do not read Japanese.
    st.markdown("#### Step 1 — your postal code")
    st.markdown(
        '<div class="caption" style="text-align:left">Everyone knows this one. We turn it '
        'into the Japanese address for you, so you never have to type Japanese.</div>',
        unsafe_allow_html=True,
    )
    pc1, pc2 = st.columns([3, 1])
    pc_input = pc1.text_input(
        "Postal code", st.session_state.get("pc_code", ""),
        placeholder="134-0088", label_visibility="collapsed",
    )
    if pc2.button("Look up", use_container_width=True):
        st.session_state.pc_code = pc_input
        found = postal_lookup(pc_input)
        if found:
            st.session_state.pc_result = found
            st.rerun()
        else:
            st.session_state.pop("pc_result", None)
            st.error(
                "Could not find that postal code. Check the 7 digits, or type the address "
                "below by hand — this lookup needs internet, the emergency itself never does."
            )
    found = st.session_state.get("pc_result")
    if found:
        st.success(f"Found: **{found['prefecture']}{found['city_ward']}** — filled in below.")

    st.markdown("#### Step 2 — the rest")
    st.warning(
        "**Anything you type yourself must be in Japanese, not romaji.** A Japanese voice "
        "reads this to the dispatcher — 'Tokyo Edogawa' comes out as noise, and the address "
        "is the one field that must be right. Numbers are fine as digits.",
        icon="⚠️",
    )

    with st.form("setup"):
        st.markdown("**Where the ambulance should come**")
        c1, c2 = st.columns(2)
        _pc = st.session_state.get("pc_result") or {}
        prefecture = c1.text_input("Prefecture 都道府県",
                                   _pc.get("prefecture") or addr.get("prefecture", ""),
                                   placeholder="東京都")
        city_ward = c2.text_input("City / ward 市区町村",
                                  _pc.get("city_ward") or addr.get("city_ward", ""),
                                  placeholder="江戸川区西葛西")
        c3, c4, c5 = st.columns([2, 2, 1])
        street_block = c3.text_input("Street & block 丁目・番地", addr.get("street_block", ""),
                                     placeholder="4丁目24-5")
        building = c4.text_input("Building name 建物名", addr.get("building", ""),
                                 placeholder="〇〇マンション")
        room = c5.text_input("Room 部屋", addr.get("room", ""), placeholder="405")

        st.markdown("**The person most likely to need help**")
        c6, c7, c8 = st.columns([2, 1, 1])
        pname = c6.text_input("Name 名前 (Japanese)", pat.get("name", ""))
        page = c7.number_input("Age", 0, 120, int(pat.get("age") or 0))
        sexes = ["female", "male", "unknown"]
        psex = c8.selectbox("Sex", sexes, index=sexes.index(pat.get("sex", "female")))
        conds = st.text_input(
            "Known conditions 持病 (Japanese, comma-separated)",
            "、".join(pat.get("known_conditions") or []),
        )

        st.markdown("**You**")
        c9, c10 = st.columns(2)
        cname = c9.text_input("Your name 名前 (Japanese)", cal.get("name", ""))
        lang_codes = list(LANGUAGE_OPTIONS)
        clang = c10.selectbox(
            "Language you will speak", lang_codes,
            index=lang_codes.index(cal.get("native_language", "en")),
            format_func=lambda c: LANGUAGE_OPTIONS[c],
        )

        if st.form_submit_button("Save", use_container_width=True):
            missing = not (prefecture and city_ward and street_block and page)
            # Romaji in the address is the failure mode that matters: it is spoken aloud as the
            # ambulance's destination. Saving is still allowed - locking the user out entirely
            # is worse - but the home screen keeps warning until it is fixed.
            # EVERY spoken field, not just the address. The patient's name, their conditions
            # and the caller's name are all read aloud by a Japanese voice too.
            romaji = [
                label for label, val in (
                    ("Prefecture", prefecture), ("City/ward", city_ward),
                    ("Street & block", street_block), ("Building", building),
                    ("Patient name", pname), ("Known conditions", conds), ("Your name", cname),
                )
                if looks_romaji(val)
            ]
            if missing:
                st.error("Prefecture, city/ward, street & block, and age are required.")
            else:
                import json as _json
                from caller_profile import PROFILE_PATH
                PROFILE_PATH.write_text(_json.dumps({
                    "address": {
                        "prefecture": prefecture, "city_ward": city_ward,
                        "street_block": street_block, "building": building, "room": room,
                    },
                    "patient": {
                        "name": pname, "age": int(page), "sex": psex,
                        "known_conditions": [
                            c.strip() for c in conds.replace("、", ",").split(",") if c.strip()
                        ],
                    },
                    "caller": {
                        "name": cname, "native_language": clang,
                        "japanese_fluency": cal.get("japanese_fluency", "limited"),
                    },
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                try:
                    PROFILE_PATH.chmod(0o600)  # owner-only; it holds a home address
                except OSError:
                    pass

                # Record the new details NOW, not during an emergency. Also deletes recordings
                # of details you just changed, so an old address does not linger on disk.
                with st.spinner("Recording your details in Japanese…"):
                    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
                    import build_audio
                    result = build_audio.build(log=lambda *_: None)
                get_data.clear()
                if result["failed"]:
                    st.error(
                        f"{result['failed']} recordings could not be made — this machine has "
                        "no Japanese voice. Run tools/build_audio.py on a machine that does "
                        "and copy data/audio/ across."
                    )
                elif romaji:
                    st.error(
                        f"Saved, but **{', '.join(romaji)}** is not in Japanese. The dispatcher "
                        "will hear this read aloud and it will not be understandable. Please fix "
                        "it before relying on this app."
                    )
                else:
                    st.success(
                        f"Saved. {result['built']} new recordings made"
                        + (f", {result['removed']} old ones deleted." if result["removed"] else ".")
                    )
                    st.session_state.phase = "idle"
                    st.rerun()

# ---- 1. Idle: the button ----
elif phase == "idle":
    if st.button("🚨  EMERGENCY", key="emergency"):
        go("dispatch_now")
    st.markdown('<div class="caption">Call 119 first. Then tap this.</div>', unsafe_allow_html=True)
    if st.button("⚙ Your details"):
        go("setup")
    # Keep warning here, not only on the setup screen. Romaji in a spoken field is not a
    # cosmetic problem - the dispatcher hears noise for the address, the name, or the medical
    # history - and the user must not be able to forget about it.
    bad = romaji_fields(profile)
    if bad:
        st.error(
            f"⚠️ **{', '.join(bad)}** {'is' if len(bad) == 1 else 'are'} not in Japanese, so "
            "cannot be read to the dispatcher. Open **Your details** and fix it.",
        )

# ---- 1b. THE FIRST 15 SECONDS. ----
# 救急です + the address need NOTHING from the pipeline: the word is a constant and the address
# is already in profile.json. This used to be the LAST question asked (old `ask_location` phase,
# step 7 of 9), so the dispatcher asked 「火事ですか、救急ですか?」 and heard silence for a full
# minute while the caller recorded, transcribed, classified and confirmed - before finally
# playing a chunk whose first word answered the original question.
# Type + location is what actually dispatches the ambulance; everything else is follow-up
# delivered while it is already en route. This is the NET119 pattern, and it is also why our
# inference latency is a polish problem rather than a safety one - the ambulance is already
# moving before the SLM has finished thinking.
elif phase == "dispatch_now":
    if "at_registered_address" not in st.session_state:
        st.session_state.at_registered_address = True

    st.markdown('<div class="status">▶ Play these to the dispatcher NOW</div>', unsafe_allow_html=True)

    # A radio, not a toggle. The old toggle showed the CURRENT state on its face
    # ("🏠 At home"), so it was unreadable whether that described the situation or was the
    # action you were about to take. A radio shows both options with one marked.
    where = st.radio(
        "Where is the emergency?",
        ["At this address", "Somewhere else"],
        index=0 if st.session_state.at_registered_address else 1,
        horizontal=True,
    )
    st.session_state.at_registered_address = where == "At this address"

    # Split into short pieces so the dispatcher can write each down, and so a repeat request
    # only costs one piece. See render_location_pieces for the measurement behind this.
    pieces = render_location_pieces(profile["address"] if st.session_state.at_registered_address else None)
    for n, piece in enumerate(pieces, 1):
        st.markdown(
            f'<div class="caption" style="text-align:left;margin-bottom:0.2rem">{n}. {piece["label"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f'<div class="briefing-jp">{piece["jp"]}</div>', unsafe_allow_html=True)
        audio = speak(piece["jp"])
        if audio:
            st.audio(audio, format="audio/wav")
        else:
            st.markdown('<div class="caption">(no Japanese voice on this machine)</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Next: symptoms →", use_container_width=True):
        go("recording")

# ---- 2. Record ----
elif phase == "recording":
    st.markdown('<div class="status">🎤 Speak now — what is happening?</div>', unsafe_allow_html=True)

    # Default to the profile's language, but let the caller override in one tap - forcing
    # the wrong language corrupts the whole transcript (e.g. more comfortable in English
    # than their registered language, mixed-language household).
    default_lang = (profile.get("caller") or {}).get("native_language", "en")
    if "stt_language" not in st.session_state:
        st.session_state.stt_language = default_lang
    codes = list(LANGUAGE_OPTIONS)
    st.session_state.stt_language = st.selectbox(
        "Speaking in", codes, index=codes.index(st.session_state.stt_language),
        format_func=lambda c: LANGUAGE_OPTIONS[c],
    )

    recorded = st.audio_input("Record", label_visibility="collapsed")
    st.markdown('<div class="caption">…or upload a .wav clip to test</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("upload", type=["wav"], label_visibility="collapsed")
    clip = recorded or uploaded
    if clip is not None:
        lang = st.session_state.stt_language
        with st.spinner("Understanding what you said…"):
            data = clip.read()
            import io as _io
            # TWO passes for a non-English caller, and they serve different readers:
            #   transcript    - the caller's OWN language. This is what they read and confirm;
            #                   showing them English they cannot read would break the safety loop.
            #   transcript_en - Whisper's English translation, fed to the classifier, whose
            #                   prompt and all 29 trigger phrases are English.
            # Measured 2026-08-14: classifying Chinese directly returned [] (every symptom
            # dropped) and Korean fabricated `no_pulse`. Translating first fixed both.
            st.session_state.transcript = transcribe(_io.BytesIO(data), lang)
            st.session_state.transcript_en = (
                st.session_state.transcript if lang == "en"
                else transcribe(_io.BytesIO(data), lang, task="translate")
            )
        go("confirm_transcript")
    if st.button("← Start over"):
        reset()

# ---- 3. Confirm the transcript ("did we hear you right?") ----
elif phase == "confirm_transcript":
    st.markdown('<div class="status">You said:</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="transcript">{st.session_state.transcript}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("✓ Yes, correct", use_container_width=True):
        with st.spinner("Understanding the emergency… (a few seconds)"):
            # The ENGLISH text - see the two-pass comment in the recording phase.
            m = slm_matches(st.session_state.transcript_en, ontology)
            st.session_state.entries = m["symptoms"] + m["events"] + m["consciousness"]
        go("confirm_symptoms")
    if c2.button("✗ Say it again", use_container_width=True):
        go("recording")

# ---- 4. Confirm understood symptoms ("did we understand you right?") ----
elif phase == "confirm_symptoms":
    st.markdown('<div class="status">We understood:</div>', unsafe_allow_html=True)
    entries = st.session_state.entries
    if entries:
        for i, e in enumerate(entries):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"### • {_humanize(e['id'])}")
            if c2.button("✕", key=f"rm_{i}"):
                entries.pop(i)
                st.rerun()
            # ASPECT: four terms (vomiting/seizure/heavy_bleeding/choking) describe something
            # that can STOP while still being worth reporting. 〜ています asserts it is ongoing,
            # which we cannot actually know. Rather than have the model guess the tense - which
            # could fail in the DANGEROUS direction, reporting "stopped" during a live seizure -
            # the human tells us here. Same principle as the awake/breathing buttons.
            # Data-driven: any entry with a "finished" form gets this control, no hard-coded list.
            if e.get("forms", {}).get("finished"):
                # Indented and explicitly named, because a bare pair of radios sitting under a
                # list of symptoms reads as ONE setting for all of them. It is per-symptom -
                # you can have vomiting ongoing while the seizure has already stopped.
                pad, body = st.columns([1, 9])
                body.radio(
                    f"Is the {_humanize(e['id'])} still happening?",
                    ["Happening now", "Has stopped"],
                    key=f"aspect_{e['id']}", horizontal=True,
                )
    else:
        st.markdown('<div class="caption">(nothing yet — add below if we missed something)</div>', unsafe_allow_html=True)

    current_ids = {e["id"] for e in entries}
    options = [
        e for section in ("consciousness_states", "symptoms", "events")
        for e in ontology[section]
        # Hide the binary statuses: the deterministic awake/breathing questions own them,
        # so letting the human also add them here would duplicate or contradict the answer.
        if e["id"] not in SLM_DISCARD and e["id"] not in current_ids
    ]
    labels = [_humanize(e["id"]) for e in options]
    c1, c2 = st.columns([4, 1])
    choice = c1.selectbox("Add", ["— add a symptom —"] + labels, label_visibility="collapsed")
    if c2.button("+ Add", use_container_width=True) and choice in labels:
        entries.append(options[labels.index(choice)])
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Looks right  →", use_container_width=True):
        # Apply the aspect choices. Replace with a COPY rather than mutating in place - these
        # dicts come from the loaded ontology, and editing them would corrupt it for later runs.
        for i, e in enumerate(entries):
            finished = e.get("forms", {}).get("finished")
            if finished and st.session_state.get(f"aspect_{e['id']}") == "Has stopped":
                entries[i] = {**e, "japanese_term": finished}
        st.session_state.extras = []
        st.session_state.need_breathing = not any(
            e["id"] in {"difficulty_breathing", "not_breathing"} for e in entries
        )
        # Circulation is the THIRD vital sign dispatchers assess (呼吸/循環/意識) - we were
        # missing it entirely until the 緊急度判定プロトコル review.
        st.session_state.need_circulation = not any(
            e["id"] in {"cold_sweat", "pale_complexion"} for e in entries
        )
        go("ask_awake")

# ---- 5. Critical field: awake? (always asked - SLM never provides it) ----
elif phase == "ask_awake":
    st.markdown('<div class="status">Is the person awake and responsive?</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    picked = None
    if c1.button("Yes", use_container_width=True):
        picked = "conscious"
    if c2.button("No", use_container_width=True):
        picked = "unconscious"
    if c3.button("Not sure", use_container_width=True):
        picked = ""
    if picked is not None:
        if picked:
            st.session_state.extras.append(_statement_from(ontology, picked))
        go("ask_breathing" if st.session_state.need_breathing else
           "ask_circulation" if st.session_state.need_circulation else "ask_patient")

# ---- 6. Critical field: breathing? (only if not already mentioned) ----
elif phase == "ask_breathing":
    st.markdown('<div class="status">Is the person breathing?</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    picked = None
    if c1.button("Yes", use_container_width=True):
        picked = ""
    if c2.button("No", use_container_width=True):
        picked = "not_breathing"
    if c3.button("Not sure", use_container_width=True):
        picked = ""
    if picked is not None:
        if picked:
            st.session_state.extras.append(_statement_from(ontology, picked))
        go("ask_circulation" if st.session_state.need_circulation else "ask_patient")

# ---- 6b. Critical field: CIRCULATION - the third vital sign. Mirrors the dispatcher's own
#      questions 「冷や汗をかいていますか？」「顔色は悪いですか？」so we pre-answer them. ----
elif phase == "ask_circulation":
    st.markdown('<div class="status">Do they look pale, or are they in a cold sweat?</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    picked = None
    if c1.button("Pale", use_container_width=True):
        picked = ["pale_complexion"]
    if c2.button("Cold sweat", use_container_width=True):
        picked = ["cold_sweat"]
    if c3.button("Both", use_container_width=True):
        picked = ["pale_complexion", "cold_sweat"]
    if c4.button("Neither / not sure", use_container_width=True):
        picked = []
    if picked is not None:
        for eid in picked:
            st.session_state.extras.append(_statement_from(ontology, eid))
        go("ask_patient")

# ---- 7. Location ----
# (The old `ask_location` phase lived here. Location is now the FIRST thing delivered, in
#  `dispatch_now` - see the comment there. Asking it last was the single worst ordering bug
#  in the flow.)

# ---- 8. Patient identity ----
elif phase == "ask_patient":
    p = profile["patient"]
    desc = f"{p['age']}-year-old {p.get('sex', '')}"
    if p.get("known_conditions"):
        desc += f" · {', '.join(p['known_conditions'])}"
    st.markdown('<div class="status">Is the emergency about this person?</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="caption">{desc}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    picked = None
    if c1.button("Yes", use_container_width=True):
        picked = True
    if c2.button("No, someone else", use_container_width=True):
        picked = False
    if picked is not None:
        st.session_state.patient_ok = picked
        go("briefing")

# ---- 9. The Japanese briefing, delivered one paced chunk at a time ----
elif phase == "briefing":
    if "chunks" not in st.session_state:
        st.session_state.chunks = build_briefing_chunks(
            st.session_state.entries, st.session_state.extras, profile, ontology,
            st.session_state.patient_ok, st.session_state.at_registered_address,
        )
        # Start at 1, not 0: chunk 0 is the emergency+location line, already delivered back in
        # `dispatch_now`. Replaying it would waste the dispatcher's time on the one thing they
        # definitely already have. min() guards the degenerate case of a single-chunk briefing.
        st.session_state.chunk_i = min(1, len(st.session_state.chunks) - 1)

    chunks = st.session_state.chunks
    i = st.session_state.chunk_i
    chunk = chunks[i]

    st.markdown(f'<div class="status">Read to 119 — part {i + 1} of {len(chunks)}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="caption">{chunk["label"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="briefing-jp">{chunk["jp"]}</div>', unsafe_allow_html=True)

    # The caller can't read Japanese, so the app says it for them. NOT autoplay - the
    # caller chooses to play it (an aid, never an automated broadcast into the 119 line).
    audio = speak(chunk["jp"])
    if audio:
        st.markdown('<div class="caption">▶ play this to the dispatcher</div>', unsafe_allow_html=True)
        st.audio(audio, format="audio/wav")
    else:
        st.markdown('<div class="caption">(no Japanese voice available on this machine)</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    # "Previous PART" (moves within the briefing) vs the "Previous STEP" button below the
    # progress bar (leaves the briefing entirely). Named apart so they cannot be confused.
    if i > 0 and c1.button("← Previous part", use_container_width=True):
        st.session_state.chunk_i -= 1
        st.rerun()
    if i < len(chunks) - 1:
        if c2.button("Next part →", use_container_width=True):
            st.session_state.chunk_i += 1
            st.rerun()
    else:
        if c2.button("Call finished →", use_container_width=True):
            go("handoff")

    with st.expander("Show the whole briefing"):
        st.markdown(
            f'<div class="briefing-jp">{"".join(c["jp"] for c in chunks)}</div>',
            unsafe_allow_html=True,
        )
    if not st.session_state.patient_ok:
        st.markdown('<div class="caption">(patient details left out — the dispatcher will ask)</div>', unsafe_allow_html=True)

# ---- 10. ON-SITE HANDOFF: hold the screen up to the arriving crew. ----
# The call is over; this is the other end of the same problem. The crew arrives to a family
# member who cannot tell them anything. 救急ボイストラ (96% of fire departments) already handles
# translating what gets said on scene - we do NOT compete with that. What it structurally cannot
# have is the PREPARED profile plus what was actually confirmed during the call. That is what
# this shows, in verified Japanese, big enough to read at arm's length.
elif phase == "handoff":
    st.markdown('<div class="status">Show this to the ambulance crew</div>', unsafe_allow_html=True)
    rows = build_handoff(
        st.session_state.entries, st.session_state.extras, profile, ontology,
        st.session_state.patient_ok, st.session_state.at_registered_address,
    )
    # Label and value on ONE line, label in a fixed-width column so all four line up and the
    # crew's eye runs straight down the values. All Japanese, nothing to scan past.
    for row in rows:
        st.markdown(
            f'<div class="briefing-jp" style="display:flex;gap:1rem;align-items:baseline;'
            f'margin-bottom:0.6rem">'
            f'<span style="flex:0 0 4.5em;opacity:0.6;font-size:1.2rem">'
            f'{HANDOFF_LABELS[row["key"]]}</span>'
            f'<span style="flex:1">{row["jp"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("← Back to briefing", use_container_width=True):
        back()
    if c2.button("✓ Done", use_container_width=True):
        reset()

# Rendered last so it sits at the bottom of every screen in the flow (returns silently on
# `idle`, which is not part of the sequence).
show_progress(phase)
