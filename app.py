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
    build_briefing_chunks, slm_matches, _statement_from, _humanize, _find_entry,
)
from briefing_template import (  # noqa: E402
    render_location_pieces, HANDOFF_LABELS, HANDOFF_LABELS_EN,
)
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
      /* Streamlit prints "Press Enter to apply" under every text box. Noise on a screen that
         should be as close to wordless as possible - and misleading here, because the buttons
         next to these boxes are what actually act. */
      [data-testid="InputInstructions"] {display: none !important;}
      /* The warm-up spinner is the FIRST thing anyone sees on a cold start, and Streamlit
         left-aligns it by default against an otherwise centred screen. */
      [data-testid="stSpinner"] {
        display: flex; justify-content: center; text-align: center;
      }
      [data-testid="stSpinner"] > div {margin: 0 auto;}
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


# What each screen contributes to `extras`. Going back has to UNDO the answer belonging to the
# screen you are returning to. Without this, a caller who answered "not breathing", went back
# and corrected it to "breathing" still sent 息をしていません - the answer they had just
# retracted, promoted to the CRITICAL chunk, driving telephone-guided CPR. `extras` is
# append-only, so nothing else ever takes an answer back out.
SCREEN_ANSWER_IDS = {
    "ask_awake": {"conscious", "unconscious"},
    "ask_breathing": {"not_breathing"},
    "ask_circulation": {"pale_complexion", "cold_sweat"},
}


def back_clearing():
    """Drop the destination screen's answer, then go back to it.

    ORDER MATTERS. The removal must happen BEFORE back(), because back() ends in st.rerun(),
    which raises to restart the script - anything written after it never executes at all.

    Reads the destination WITHOUT popping it; back() does that. Reading it rather than
    hard-coding one is what makes the skipped-screen paths correct: ask_patient is reached from
    circulation, breathing or awake depending on what the caller already mentioned, so which
    answer needs undoing is not knowable from the current screen alone.
    """
    hist = st.session_state.get("history", [])
    if not hist:
        return
    ids = SCREEN_ANSWER_IDS.get(hist[-1], set())
    if ids:
        st.session_state.extras = [
            s for s in st.session_state.get("extras", []) if s.get("id") not in ids
        ]
    back()


# Screens that get the generic "previous step" button. Deliberately NOT every screen:
#   idle                - it IS the start; there is nothing behind it.
#   confirm_transcript  - already has "Say it again", which is the same move but clearer.
#                         A generic back would also land on `recording` with the clip still
#                         loaded, which re-transcribes immediately and looks like nothing
#                         happened.
# `briefing` DOES get one: it has its own back, but that only walks the chunks, so from the
# final screen there was no way back to an earlier question at all. The two are disambiguated
# by name - "Previous part" moves within the briefing, "Previous step" leaves it.
# ask_breathing / ask_circulation / ask_patient are NOT here: they carry their own button that
# calls back_clearing() first. The generic one would leave the retracted answer behind.
BACKABLE = {"dispatch_now", "recording", "confirm_symptoms", "ask_awake", "briefing"}


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
              "transcript_en", "other_form", "other_patient"):
        st.session_state.pop(k, None)
    # The per-symptom aspect radios are keyed by symptom id, so they are not in the list above.
    # Left behind, a previous call's "Has stopped" would silently pre-select on the next one.
    for k in [k for k in st.session_state if k.startswith("aspect_")]:
        st.session_state.pop(k, None)
    st.session_state.phase = "idle"
    st.rerun()


profile, ontology = get_data()


def _briefing_profile():
    """The profile the briefing should speak from.

    When the call is about SOMEONE ELSE, the caller may still have told us their age and
    conditions - see ask_patient. Swap those details in for this call only. profile.json is
    never touched: it is another person's medical information and storing it silently would
    be wrong.
    """
    other = st.session_state.get("other_patient")
    if not other:
        return profile
    merged = dict(profile)
    merged["patient"] = dict(profile["patient"], **other)
    return merged



@st.cache_resource(show_spinner="Preparing the emergency assistant…")
def warm_brain():
    """Load + compile the brain when the app OPENS, not during an emergency. Cached, so it
    runs once per server session; the on-disk compile cache makes even that fast after the
    first-ever launch.

    IT MUST CALL THE REAL classify(), NOT A SHORTCUT. Beyond loading weights, this call is what
    POPULATES THE PREFIX CACHE: Stage A's prompt is system + few-shot + the 31-entry menu +
    transcript, and ~800 of those tokens are identical on every call. Running the genuine
    prompt here means the first real emergency finds the cache already warm.

    Replace this with a cheaper warm-up (loading the model without a full classify, or a
    trimmed prompt) and the cache stays empty, so THE FIRST EMERGENCY OF THE DAY pays the
    uncached ~42s instead of ~4s - the worst possible call to be slow. Measured 2026-08-24."""
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

    # POSTAL CODE FIRST, and outside the form - a non-submit button inside an st.form does
    # nothing until submit, and this has to work on its own. Placed at the top because it is
    # the step that saves the user from the impossible task: typing their own address in
    # Japanese when they do not read Japanese.
    st.markdown("#### Step 1 — your postal code")
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
            st.error("Postal code not found. Check the digits, or use the map below.")
    found = st.session_state.get("pc_result")
    if found:
        # The ROMAJI READBACK is the point here, not decoration. Showing only
        # 東京都江戸川区西葛西 asked a user who cannot read Japanese to confirm the single most
        # critical field on faith. The romaji is a deterministic kana conversion, not a
        # translation - the Japanese stays authoritative.
        st.success(f"**{found['prefecture']}{found['city_ward']}**")
        if found.get("romaji"):
            st.markdown(
                f'<div class="caption" style="text-align:left;margin-top:-0.6rem">'
                f'{found["romaji"]}</div>',
                unsafe_allow_html=True,
            )

    # ---- MAP PIN: the universal mechanism. POINT, DO NOT TYPE. ----
    # A postal code still assumes the user can name their own address. This does not: 国土地理院
    # (Japan's national mapping authority) turns any coordinate into an official Japanese place
    # name, so it works for a home, a dormitory, a school playground or a community hall
    # identically. Tested on a park with no postal address - see src/postal.py.
    #
    # Typing was measured to be the WORSE option regardless of language: geocoding
    # "Nishikasai 6-15-2" returned 西葛西一丁目, silently ignoring the numbers.
    #
    # SETUP-TIME ONLY. No map and no network are involved during an emergency.
    # STAYS OPEN once engaged. It used to be `expanded=not found`, so clicking your building
    # set a result -> rerun -> the map COLLAPSED, hiding the confirmation you had just produced.
    map_open = st.session_state.get("map_open", False) or not found
    # THE MAP IS THE MAIN MECHANISM, so its instruction cannot be vague. "Click your building"
    # assumed the user already knew the map was zoomed to their street, that clicking sets an
    # address, and that this is how the ambulance is told where to come. Founder, 2026-08-23:
    # "Click your building is a vague instruction... That feature is the main thing, so that
    # must be clear." Now it states, in order: what to do, how to get there, and what happens.
    step = "Step 2" if found else "Step 1"
    with st.expander(f"📍 {step} — find it on the map", expanded=map_open):
        st.session_state.map_open = True
        # TWO STEPS, NAMED, POINTING AT THE CONTROL THAT DOES IT.
        # A paragraph explaining the mechanism was the wrong shape: the user does not need to
        # understand how the map works, they need to know which thing to press first. The
        # LocateControl crosshair was already on the map and nothing ever told anyone it was
        # there, so the one control that gets you to your own street was invisible.
        # Founder, 2026-08-23: "how will they know that is how they will get near them".
        st.markdown(
            '<div class="caption" style="text-align:left;font-size:1.15rem">'
            # The glyph here MUST look like the button actually on the map. It was the 📍
            # emoji, which renders bright red, while the control in the corner is a dark grey
            # map-marker - so the instruction pointed at something the user could not find.
            # This is an inline SVG of the same marker, in the same colour.
            '<b>1.</b> Tap '
            '<span style="display:inline-flex;vertical-align:-3px;background:#fff;'
            'border:1px solid #999;border-radius:4px;padding:2px 4px">'
            '<svg width="13" height="16" viewBox="0 0 384 512" fill="#3b3b3b">'
            '<path d="M192 0C86 0 0 86 0 192c0 77 27 99 173 309 9 13 29 13 38 0'
            'C357 291 384 269 384 192 384 86 298 0 192 0zm0 272a80 80 0 110-160 80 80 0 010 160z"/>'
            '</svg></span>'
            ' on the map to jump to where you are '
            '&nbsp;→&nbsp; <b>2.</b> Tap your building'
            '</div>',
            unsafe_allow_html=True,
        )
        import folium
        from streamlit_folium import st_folium
        from postal import reverse_geocode, search_place

        # SEARCH BOX. Type a nearby landmark in ANY alphabet - "Kasai Rinkai Park", "Nishikasai
        # station" - and the map jumps there. Verified that romaji input returns Japanese places.
        # It only MOVES THE MAP; the click is still what fixes the address, because typed street
        # numbers were measured unreliable ("Nishikasai 6-15-2" -> 西葛西一丁目, numbers dropped).
        sc1, sc2 = st.columns([3, 1])
        place_q = sc1.text_input(
            "Search a place", st.session_state.get("map_query", ""),
            placeholder="Nishikasai station  /  西葛西駅", label_visibility="collapsed",
        )
        if sc2.button("Search", use_container_width=True):
            st.session_state.map_query = place_q
            hits = search_place(place_q)
            if hits:
                st.session_state.map_hits = hits
                st.session_state.map_centre = [hits[0]["lat"], hits[0]["lon"]]
                st.session_state.map_zoom = 18
                st.session_state.map_open = True
                st.rerun()
            elif hits is None:
                # Unreachable or rate-limited - the query itself may be perfectly good, so do
                # NOT tell the user to rewrite it.
                st.session_state.pop("map_hits", None)
                st.warning("Search unavailable — try again in a moment.")
            else:
                st.session_state.pop("map_hits", None)
                st.warning("No place by that name. Try a station, park or landmark nearby.")

        hits = st.session_state.get("map_hits") or []
        if len(hits) > 1:
            labels = [h["label"][:70] for h in hits]
            pick = st.radio("Which one?", labels, index=0, key="map_hit_pick")
            chosen = hits[labels.index(pick)]
            if st.session_state.get("map_centre") != [chosen["lat"], chosen["lon"]]:
                st.session_state.map_centre = [chosen["lat"], chosen["lon"]]
                st.rerun()

        # Centre on the search result / postal-code result if there is one, else Tokyo.
        centre = st.session_state.get("map_centre", [35.6812, 139.7671])
        from folium.plugins import Fullscreen, LocateControl, MousePosition

        # max_zoom 21 with max_native_zoom 18 on each layer = OVER-ZOOM. Verified 2026-08-21
        # that GSI serves tiles to zoom 18 and 404s at 19+, so capping the map at 18 hard-stopped
        # zooming exactly when the user was trying to pick ONE BUILDING out of a row of them.
        # Past 18 Leaflet upscales the zoom-18 tile: blurrier, but the pin can be placed
        # precisely, which is the whole point. Standard practice in mapping apps.
        fmap = folium.Map(
            location=centre, zoom_start=st.session_state.get("map_zoom", 17),
            tiles=None, control_scale=True,  # scale bar: a sense of distance while zooming
            max_zoom=21,
        )
        # THREE GSI layers. The AERIAL one is the important addition: people recognise their own
        # building from a photo far faster than from a street map, which is the entire task here.
        # All three verified reachable 2026-08-21.
        # THREE layers, chosen for BUILDING VISIBILITY - the founder's building is ~2 years old
        # and absent from aerial photos. That is expected: photos refresh every few years, but
        # OSM is community VECTOR data updated continuously, so new buildings appear there far
        # sooner. Hence OSM first, photos second.
        #
        # NOTE THE ADDRESS DOES NOT DEPEND ON ANY OF THIS. GSI maps the COORDINATE to a 丁目, so
        # clicking the right patch of ground gives the right address even where nothing is drawn.
        # The imagery only helps the user aim.
        folium.TileLayer(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr="© OpenStreetMap contributors", name="Map (newest buildings)",
            max_zoom=21, max_native_zoom=19).add_to(fmap)
        folium.TileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles © Esri", name="Satellite",
            max_zoom=21, max_native_zoom=20).add_to(fmap)
        folium.TileLayer(
            "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
            attr="国土地理院", name="Map (official Japanese)",
            max_zoom=21, max_native_zoom=18).add_to(fmap)
        folium.LayerControl(collapsed=False, position="topright").add_to(fmap)

        Fullscreen(position="topleft", title="Bigger map").add_to(fmap)
        # Jumps to roughly where this device is. On a LAPTOP this is WiFi-based and only
        # accurate to tens/hundreds of metres - useless for a room, but it saves all the
        # panning, and the user still clicks the exact building.
        # Same wording as step 1 above, so the instruction and the control match.
        # Location-pin glyph rather than Leaflet's default crosshair - the pin is the symbol
        # people already associate with "find me" from every maps app they have used.
        # NOTE: deliberately NOT Google's actual logo, which is trademarked.
        LocateControl(
            position="topleft",
            strings={"title": "Jump to where I am now"},
            icon="fa fa-map-marker",
        ).add_to(fmap)
        MousePosition(position="bottomleft", prefix="").add_to(fmap)

        if st.session_state.get("map_pin"):
            folium.Marker(
                st.session_state["map_pin"], icon=folium.Icon(color="red", icon="home"),
                tooltip="Click elsewhere to move this",
            ).add_to(fmap)

        clicked = st_folium(fmap, height=420, width=None, key="addr_map")
        if clicked and clicked.get("last_clicked"):
            lat = clicked["last_clicked"]["lat"]
            lon = clicked["last_clicked"]["lng"]
            if st.session_state.get("map_pin") != [lat, lon]:
                st.session_state.map_pin = [lat, lon]
                st.session_state.map_centre = [lat, lon]
                with st.spinner("Reading the Japanese address…"):
                    got = reverse_geocode(lat, lon)
                if got:
                    # town (丁目) goes into street_block; the user adds only the digits after it.
                    # KEEP THE POSTAL LOOKUP'S KANA if the map landed in the same city.
                    # This used to REPLACE pc_result outright, which silently destroyed the
                    # Japan Post reading captured moments earlier - and since the intended flow
                    # is postal code (step 1) THEN map (step 2), the reading was being wiped on
                    # essentially every run. The app then fell back to speaking kanji, which is
                    # the guessing this was built to eliminate.
                    #
                    # Dropped when the map moves to a DIFFERENT city, because the old reading
                    # would then belong to somewhere else - a wrong reading is worse than none.
                    prev = st.session_state.get("pc_result") or {}
                    # Postal lookup contains ward + town (e.g. 江東区南砂), while GSI
                    # returns the ward alone (江東区). The old comparison was backwards,
                    # so the normal postal-code → map flow always discarded the published
                    # kana reading. Preserve it only when the map's municipality is a prefix
                    # of the postal result: same place, not merely a similar-looking town.
                    same_place = (
                        prev.get("prefecture") == got["prefecture"]
                        and bool(prev.get("city_ward"))
                        and prev["city_ward"].startswith(got["city_ward"])
                    )
                    st.session_state.pc_result = {
                        "prefecture": got["prefecture"], "city_ward": got["city_ward"],
                        "kana": prev.get("kana", "") if same_place else "",
                    }
                    st.session_state.map_town = got["town"]
                    # Building name too, if OSM knows it - a LOOKUP, never a guess. Often ""
                    # for ordinary apartment blocks, which is why the field stays optional.
                    from postal import building_name_at
                    st.session_state.map_building = building_name_at(lat, lon)
                    # Same readback reason as the postal lookup: the user cannot check kanji.
                    # kana_to_romaji() was used here and could NEVER work - it converts kana and
                    # bails on kanji, which every place name is. A second, independent lookup
                    # answers the same coordinate in English instead.
                    from postal import romaji_address_at
                    st.session_state.map_town_romaji = romaji_address_at(lat, lon)
                    st.session_state.map_open = True
                    st.rerun()
                else:
                    st.error(
                        "Could not read an address there. Try clicking closer to a building, "
                        "or use the postal code above."
                    )
        if st.session_state.get("map_town"):
            st.success(
                f"**{st.session_state.pc_result['prefecture']}"
                f"{st.session_state.pc_result['city_ward']}{st.session_state['map_town']}**"
            )
            st.caption("This is where the ambulance will be sent:")
            # THE ENGLISH IS MANDATORY, the Japanese is shown alongside for transparency.
            # Without this the map path asked a user who cannot read kanji to confirm the one
            # field that decides where the ambulance goes. Shown only - never stored, never spoken.
            #
            # THREE OUTCOMES, ALL VISIBLE. Showing nothing on failure was the bug: the user
            # could not tell whether the app had no English name, or had failed to ask.
            romaji = st.session_state.get("map_town_romaji")
            if romaji:
                st.markdown(
                    f'<div class="caption" style="text-align:left;margin-top:-0.6rem">'
                    f'{romaji}</div>',
                    unsafe_allow_html=True,
                )
            elif romaji is None:
                st.warning("Could not fetch the English name just now. Tap the building again "
                           "to retry — the Japanese address above is already correct.", icon="⚠️")
            else:
                st.info("No English name exists for this spot. The Japanese address above is "
                        "still correct and is what the ambulance will use.", icon="ℹ️")

    st.markdown("#### Step 2 — the rest")

    with st.form("setup"):
        st.markdown("**Where the ambulance should come**")
        c1, c2 = st.columns(2)
        _pc = st.session_state.get("pc_result") or {}
        prefecture = c1.text_input("Prefecture",
                                   _pc.get("prefecture") or addr.get("prefecture", ""),
                                   placeholder="東京都")
        city_ward = c2.text_input("City / ward",
                                  _pc.get("city_ward") or addr.get("city_ward", ""),
                                  placeholder="江戸川区西葛西")
        # SPLIT INTO TWO BOXES, deliberately. It used to be ONE field pre-filled with 南砂四丁目
        # that the user had to APPEND "24-5" to - nobody would guess that. Now the auto-filled
        # part and the part they must type are visibly separate, and the empty box makes the
        # remaining task obvious.
        #
        # This split exists because the 番地 CANNOT be derived from a map click in Japan (lot
        # numbers follow registration order, not position - see OPEN_DECISIONS). The map gives
        # the kanji; the resident gives the digits, which need no language.
        c3, c3b = st.columns([2, 1])
        area = c3.text_input(
            "Area (filled by map or postal code)",
            # `area` has its OWN stored key. Reading the joined `street_block` here would reload
            # "南砂四丁目24-5" into this box while the number also sat in the box beside it, and
            # the next save would produce "南砂四丁目24-524-5".
            st.session_state.get("map_town") or addr.get("area") or addr.get("street_block", ""),
            placeholder="南砂四丁目",
        )
        block_no = c3b.text_input(
            "Block number — type this", addr.get("block_number", ""), placeholder="24-5",
        )
        c4, c5 = st.columns([2, 1])
        building = c4.text_input(
            "Building name",
            st.session_state.get("map_building") or addr.get("building", ""),
            placeholder="〇〇マンション")
        room = c5.text_input("Room", addr.get("room", ""), placeholder="405")
        # Stored joined, because that is how it is spoken as one unit; block_number is kept
        # separately too so re-opening setup shows the two boxes correctly instead of dumping
        # the whole string back into the first one.
        street_block = f"{area}{block_no}".strip()

        st.markdown("**The person most likely to need help**")
        c6, c7, c8 = st.columns([2, 1, 1])
        pname = c6.text_input("Name", pat.get("name", ""))
        page = c7.number_input("Age", 0, 120, int(pat.get("age") or 0))
        sexes = ["female", "male", "unknown"]
        psex = c8.selectbox("Sex", sexes, index=sexes.index(pat.get("sex", "female")))
        # PICK FROM A CLOSED LIST, NEVER TYPE. This was a free-text box, so a profile ended up
        # holding "Heart problem, low blood pressure" - English words fed into 持病は{...}です
        # and read aloud by a Japanese voice as literal noise. Exactly the romaji problem the
        # address lookups were built to eliminate, in the one field that never got a lookup.
        #
        # You see ENGLISH, the profile stores JAPANESE. Same rule as the address: the user
        # never has to produce Japanese, and no model ever invents any.
        _cond_by_en = {c["label_en"]: c for c in ontology.get("conditions", [])}
        _cond_by_jp = {c["japanese_term"]: c for c in ontology.get("conditions", [])}
        _other = ontology.get("condition_other", {})
        _groups = ontology.get("condition_groups", {})

        # Grouped by body system so a 27-item list stays scannable, and so we can say plainly
        # that no domain of illness is missing. Setup is a CALM task, unlike the emergency
        # flow - the constraint here is scannability, not speed.
        def _fmt(en):
            c = _cond_by_en.get(en)
            return f"{_groups.get(c['group'], '')} — {en}" if c else en

        _saved = pat.get("known_conditions") or []
        _default = [_cond_by_jp[j]["label_en"] for j in _saved if j in _cond_by_jp]
        if _other and _other.get("japanese_term") in _saved:
            _default.append(_other["label_en"])

        _options = sorted(_cond_by_en, key=lambda en: (_cond_by_en[en]["group"], en))
        if _other:
            _options.append(_other["label_en"])

        cond_labels = st.multiselect(
            "Known conditions — type to search, pick as many as apply",
            _options, default=_default, format_func=_fmt,
        )
        # Stored as Japanese. "Other" emits 持病があります - says history EXISTS without naming
        # it, so the crew knows to ask and we never invent a disease name.
        cond_list = [
            (_other if _other and l == _other.get("label_en") else _cond_by_en[l])["japanese_term"]
            for l in cond_labels
        ]
        conds = "、".join(cond_list)
        if _saved and not _default:
            st.warning(
                f"Previous entry could not be matched to the list and will be replaced: "
                f"{'、'.join(_saved)}", icon="⚠️")

        st.markdown("**You**")
        c9, c10 = st.columns(2)
        cname = c9.text_input("Your name", cal.get("name", ""))
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
            # Build the profile FIRST, then check it, then save the same object. This used to
            # inline its own copy of the romaji check with its own field labels - a second
            # implementation of romaji_fields() that promptly drifted: it still said
            # "Street & block" after that input was split into "Area" and "Block number", so
            # the warning named a field no longer on screen. One definition now, in
            # caller_profile.romaji_fields().
            new_profile = {
                "address": {
                    "prefecture": prefecture, "city_ward": city_ward,
                    # Japan Post's PUBLISHED READING for this postal code. This is what the
                    # app actually speaks - see spoken_address(). Kanji is what we show;
                    # kana is what we say, because proper-noun readings cannot be inferred.
                    "kana": (st.session_state.get("pc_result") or {}).get("kana", ""),
                    "street_block": street_block,  # joined - what gets spoken
                    "area": area, "block_number": block_no,  # parts, for re-editing
                    "building": building, "room": room,
                },
                "patient": {
                    "name": pname, "age": int(page), "sex": psex,
                    "known_conditions": cond_list,
                },
                "caller": {
                    "name": cname, "native_language": clang,
                    "japanese_fluency": cal.get("japanese_fluency", "limited"),
                },
            }
            romaji = romaji_fields(new_profile)

            if missing:
                st.error("Prefecture, city/ward, street & block, and age are required.")
            else:
                import json as _json
                from caller_profile import PROFILE_PATH
                PROFILE_PATH.write_text(
                    _json.dumps(new_profile, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                try:
                    PROFILE_PATH.chmod(0o600)  # owner-only; it holds a home address
                except OSError:
                    pass

                # Record the new details NOW, not during an emergency. Also deletes recordings
                # of details you just changed, so an old address does not linger on disk.
                with st.spinner("Recording your details in Japanese…"):
                    from tools import build_audio
                    result = build_audio.build(log=lambda *_: None)
                get_data.clear()
                if result["failed"]:
                    st.error(
                        f"{result['failed']} recordings could not be made — this machine has "
                        "no Japanese voice. Run tools/build_audio.py on a machine that does "
                        "and copy data/audio/ across."
                    )
                elif romaji:
                    st.error(f"Saved. **{', '.join(romaji)}** still needs to be in Japanese.")
                else:
                    st.success(
                        f"Saved. {result['built']} new recordings made"
                        + (f", {result['removed']} old ones deleted." if result["removed"] else ".")
                    )
                    # Clear the map/postal SCRATCH state. It has served its purpose - the values
                    # are now in profile.json. Left behind, `map_town` would OVERRIDE the saved
                    # street_block next time setup opens (the field reads map_town first), so an
                    # edit made after pinning would appear to revert.
                    for k in ("map_pin", "map_centre", "map_zoom", "map_town", "map_hits",
                              "map_query", "map_open", "pc_result", "pc_code", "map_building"):
                        st.session_state.pop(k, None)
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
        st.error(f"⚠️ Not in Japanese: **{', '.join(bad)}**")

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
    # NO "am I at this address?" QUESTION ANY MORE (removed 2026-08-20, founder's observation).
    # You have to be physically AT the device to use the app, so the emergency is wherever the
    # device is - and the device lives at the registered address. The branch was incoherent with
    # the product's own premise, and its Japanese ("I am at a different place") was meaningless
    # to a dispatcher who does not know a registered address exists.
    #
    # The edge cases do not rescue it: for a neighbour's flat or the garden the registered
    # address is still the right building, and saying "I don't know the address" would DISCARD
    # good information. A device carried elsewhere is a setup problem, not an emergency-time one.
    #
    # And nothing is lost by removing it: the address is already THREE SEPARATE play buttons,
    # so a caller who genuinely is not there simply does not press them. One less decision on
    # the most time-critical screen, which is the UI principle for this whole app.
    st.session_state.at_registered_address = True

    st.markdown('<div class="status">▶ Play these to the dispatcher NOW</div>', unsafe_allow_html=True)

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
        # BOTH DIRECTIONS, every pass. This used to only ever swap IN the finished form, so a
        # caller who went back and changed "Has stopped" to "Happening now" kept the past tense:
        # japanese_term had already been overwritten and nothing restored it. Same shape as the
        # back-navigation bug - a forward action wrote, and nothing unwrote. The ongoing wording
        # is read back from the ontology, because by the second pass the entry no longer has it.
        for i, e in enumerate(entries):
            finished = e.get("forms", {}).get("finished")
            if not finished:
                continue
            stopped = st.session_state.get(f"aspect_{e['id']}") == "Has stopped"
            ongoing = _find_entry(ontology, e["id"])["japanese_term"]
            entries[i] = {**e, "japanese_term": finished if stopped else ongoing}
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
    if st.button("← Previous step", key=f"back_{phase}"):
        back_clearing()
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
    if st.button("← Previous step", key=f"back_{phase}"):
        back_clearing()
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
    # ENGLISH ON SCREEN, JAPANESE UNDERNEATH - the same rule as the whole setup screen.
    # This showed the stored 高血圧、糖尿病 to a user defined as someone who cannot read
    # Japanese, and asked them to confirm it.
    _en = {c["japanese_term"]: c["label_en"] for c in ontology.get("conditions", [])}
    desc = f"{p['age']}-year-old {p.get('sex', '')}"
    if p.get("known_conditions"):
        desc += " · " + ", ".join(_en.get(c, c) for c in p["known_conditions"])
    st.markdown('<div class="status">Is the emergency about this person?</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="caption">{desc}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("Yes", use_container_width=True):
        st.session_state.patient_ok = True
        st.session_state.pop("other_patient", None)
        # Also close the "someone else" form. Answering "No, someone else" and then changing
        # your mind to "Yes" left it open, so returning to this screen later showed a
        # half-filled form for a patient we had already discarded.
        st.session_state.pop("other_form", None)
        go("briefing")
    if c2.button("No, someone else", use_container_width=True):
        st.session_state.other_form = True
        st.session_state.patient_ok = False
        st.rerun()
    if st.button("← Previous step", key=f"back_{phase}"):
        back_clearing()

    # "No" used to go straight to the briefing with ALL patient details omitted - safe, but it
    # threw away information the caller HAS. If your neighbour collapses you still know roughly
    # how old they are. This asks for that instead of discarding it.
    # Used for THIS CALL ONLY and never written to profile.json: it is someone else's medical
    # information, and storing it silently would be wrong.
    if st.session_state.get("other_form"):
        st.markdown('<div class="caption">Tell us what you know about them. '
                    'Skip anything you are unsure of.</div>', unsafe_allow_html=True)
        with st.form("other_patient"):
            o1, o2 = st.columns(2)
            oage = o1.number_input("Age (0 = unknown)", 0, 120, 0)
            osex = o2.selectbox("Sex", ["unknown", "female", "male"])
            _by_en = {c["label_en"]: c["japanese_term"] for c in ontology.get("conditions", [])}
            oconds = st.multiselect("Known conditions, if you know any", sorted(_by_en))
            if st.form_submit_button("Continue", use_container_width=True):
                st.session_state.other_patient = {
                    "age": int(oage) or None, "sex": osex, "name": None,
                    "known_conditions": [_by_en[c] for c in oconds],
                }
                # A caller may know a condition or sex but not an age. The temporary profile
                # deliberately omits unknown fields, so it is safe to include the information
                # they *do* know; tying this to age silently threw the rest away.
                st.session_state.patient_ok = True
                st.session_state.other_form = False
                go("briefing")
        if st.button("Skip — I do not know anything about them", use_container_width=True):
            st.session_state.pop("other_patient", None)
            st.session_state.patient_ok = False
            st.session_state.other_form = False
            go("briefing")

# ---- 9. The Japanese briefing, delivered one paced chunk at a time ----
elif phase == "briefing":
    if "chunks" not in st.session_state:
        st.session_state.chunks = build_briefing_chunks(
            st.session_state.entries, st.session_state.extras, _briefing_profile(), ontology,
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
    st.markdown('<div class="status">Show this to the ambulance crew when they arrive</div>', unsafe_allow_html=True)
    rows = build_handoff(
        st.session_state.entries, st.session_state.extras, _briefing_profile(), ontology,
        st.session_state.patient_ok, st.session_state.at_registered_address,
    )
    # DEMO ONLY. The crew screen is Japanese-only on purpose - that is correct for the people
    # who actually read it. But an Intel judge cannot read it at all, so the whole point of the
    # screen is invisible in a presentation. This toggle is OFF by default and never appears in
    # the real flow's path; it exists so the demo can show what the crew is being told.
    show_en = st.toggle("Show English", value=False)

    # ONE LINE PER ITEM, not a paragraph. A crew member reading a held-up phone in a hallway has
    # about three seconds. Symptoms used to be joined with 。 into a single cell, making the row
    # they most need to scan the one row that read as a run-on sentence.
    for row in rows:
        items = ""
        for l in row.get("lines") or [{"jp": row["jp"], "en": "", "critical": False}]:
            # Cardiac-arrest findings must not look identical to a headache.
            style = ("color:#ff6b6b;font-weight:700;font-size:1.85rem"
                     if l["critical"] else "")
            items += f'<div style="{style}">{l["jp"]}</div>'
            if show_en and l["en"]:
                items += (f'<div style="opacity:0.45;font-size:0.95rem;'
                          f'margin-bottom:0.35rem">{l["en"]}</div>')
        label = HANDOFF_LABELS[row["key"]]
        if show_en:
            label += f'<div style="font-size:0.8rem;opacity:0.5">{HANDOFF_LABELS_EN[row["key"]]}</div>'
        st.markdown(
            f'<div class="briefing-jp" style="display:flex;gap:1rem;align-items:baseline;'
            f'margin-bottom:0.6rem">'
            f'<span style="flex:0 0 4.5em;opacity:0.6;font-size:1.2rem">{label}</span>'
            f'<span style="flex:1">{items}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    # No "Done" button, deliberately - it read as the natural thing to press after playing the
    # briefing, but it RESETS the app while the crew is still in the room.
    # "Home" is the deliberate exit instead: named for where it goes, placed away from the
    # briefing button, and secondary so it is not the obvious next tap.
    h1, h2 = st.columns([2, 1])
    if h1.button("← Back to briefing", use_container_width=True):
        back()
    if h2.button("🏠 Home", use_container_width=True):
        reset()

# Rendered last so it sits at the bottom of every screen in the flow (returns silently on
# `idle`, which is not part of the sequence).
show_progress(phase)
