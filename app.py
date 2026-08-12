"""Kyūkyū-Bridge - one-button emergency UI (Streamlit).
Flow: EMERGENCY -> speak/upload -> Whisper -> confirm transcript -> SLM brain ->
confirm understood symptoms -> breathing/awake -> location -> patient -> Japanese briefing.
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Use the fast INT8 OpenVINO brain if it's been converted.
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "qwen2.5-3b-ov-int8")
if os.path.isdir(_MODEL_DIR):
    os.environ.setdefault("SLM_OV_DIR", _MODEL_DIR)

from pipeline import (  # noqa: E402
    build_briefing_chunks, slm_matches, _statement_from, _format_address, _humanize,
)
from slm_classify import SLM_DISCARD  # noqa: E402
from ontology import load_ontology  # noqa: E402
from caller_profile import load_profile  # noqa: E402

st.set_page_config(page_title="Kyūkyū-Bridge", page_icon="🚑", layout="centered")

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
    return load_profile(), load_ontology()


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


def transcribe(file_like, language: str):
    """Delegates to src/stt.py so the app and CLI share one implementation."""
    from stt import transcribe as _transcribe
    return _transcribe(file_like, language=language)


def go(phase):
    st.session_state.phase = phase
    st.rerun()


def reset():
    for k in ("phase", "transcript", "entries", "extras", "need_breathing",
              "need_circulation", "at_home", "patient_ok", "chunks", "chunk_i", "stt_language"):
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


# ---- 1. Idle: the button ----
if phase == "idle":
    if st.button("🚨  EMERGENCY", key="emergency"):
        go("recording")
    st.markdown('<div class="caption">Tap the button, then speak in your language.</div>', unsafe_allow_html=True)

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
        with st.spinner("Understanding what you said…"):
            st.session_state.transcript = transcribe(clip, st.session_state.stt_language)
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
            m = slm_matches(st.session_state.transcript, ontology)
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
                st.radio(
                    "aspect", ["Happening now", "Has stopped"],
                    key=f"aspect_{e['id']}", horizontal=True, label_visibility="collapsed",
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
           "ask_circulation" if st.session_state.need_circulation else "ask_location")

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
        go("ask_circulation" if st.session_state.need_circulation else "ask_location")

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
        go("ask_location")

# ---- 7. Location ----
elif phase == "ask_location":
    st.markdown('<div class="status">Is the emergency at your home address?</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="caption">{_format_address(profile["address"])}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    picked = None
    if c1.button("Yes, at home", use_container_width=True):
        picked = True
    if c2.button("No, somewhere else", use_container_width=True):
        picked = False
    if picked is not None:
        st.session_state.at_home = picked
        go("ask_patient")

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
            st.session_state.patient_ok, st.session_state.at_home,
        )
        st.session_state.chunk_i = 0

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
    if i > 0 and c1.button("← Back", use_container_width=True):
        st.session_state.chunk_i -= 1
        st.rerun()
    if i < len(chunks) - 1:
        if c2.button("Next part →", use_container_width=True):
            st.session_state.chunk_i += 1
            st.rerun()
    else:
        if c2.button("✓ Done", use_container_width=True):
            reset()

    with st.expander("Show the whole briefing"):
        st.markdown(
            f'<div class="briefing-jp">{"".join(c["jp"] for c in chunks)}</div>',
            unsafe_allow_html=True,
        )
    if not st.session_state.patient_ok:
        st.markdown('<div class="caption">(patient details left out — the dispatcher will ask)</div>', unsafe_allow_html=True)
