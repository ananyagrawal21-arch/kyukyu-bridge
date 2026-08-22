"""Japanese postal code -> Japanese address, so the caller never has to type Japanese.

THE PROBLEM THIS SOLVES
    Our user is, by definition, someone who does not speak Japanese - yet the address must be
    stored in Japanese, because a Japanese voice reads it to the dispatcher. Typing 東京都江戸川区
    is exactly what they cannot do, and romaji comes out as noise. Measured: a profile reading
    "Tokyo / Edogawa / 4 chome" produced 「場所はTokyoEdogawa4 chomeです。」 - unusable.

    Everyone knows their 7-digit postal code. It is on every bill, form and delivery slip. One
    lookup turns it into correct Japanese, and the hardest part of setup disappears.

THE NETWORK BOUNDARY - read this before changing anything here
    This is the ONLY code in the project that touches the network, and it runs ONLY on the
    setup screen, ONLY when the user presses "Look up". The result is written into
    profile.json and never fetched again.

    An EMERGENCY never reaches this file. Setup is a calm, one-time, connected activity (you
    downloaded the app somehow); the emergency path stays completely offline, which is the
    whole point of the project. Failure here is not fatal - the user can still type the
    address by hand.

    A fully offline version is possible by bundling Japan Post's KEN_ALL dataset (~120k rows).
    Their direct download blocks automated fetches, so that is a manual step for later; this
    module's interface would not change.
"""
import json
import re
import urllib.error
import unicodedata
import urllib.parse
import urllib.request

# Free, no API key, returns kanji. Public postal data.
_ENDPOINT = "https://zipcloud.ibsnet.co.jp/api/search?zipcode="
_TIMEOUT = 6  # setup should never hang; the user can always type it manually


_JAPANESE = re.compile(r"[぀-ヿ一-鿿ｦ-ﾟ]")
_LATIN = re.compile(r"[A-Za-z]")


def looks_romaji(text: str) -> bool:
    """Roman letters with no Japanese - i.e. text a Japanese TTS voice cannot read.

    Shared by app.py (setup screen) and tools/setup_profile.py (terminal fallback), so the
    two entry points cannot drift into disagreeing about what counts as romaji.

    Digits are NOT flagged - a Japanese voice reads "405" correctly, so a numbers-only room
    number must not false-positive.
    """
    t = text or ""
    return bool(_LATIN.search(t)) and not _JAPANESE.search(t)


def normalise(code: str) -> str:
    """Digits only: '134-0088', '１３４−００８８' and '134 0088' all mean the same thing."""
    trans = str.maketrans("０１２３４５６７８９", "0123456789")
    return "".join(c for c in (code or "").translate(trans) if c.isdigit())


def lookup(code: str):
    """{'prefecture', 'city_ward'} for a postal code, or None.

    city_ward merges the API's ward and town fields (江戸川区 + 西葛西), because that is how the
    address is spoken as one unit before the block numbers.
    """
    digits = normalise(code)
    if len(digits) != 7:
        return None
    try:
        with urllib.request.urlopen(_ENDPOINT + digits, timeout=_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None  # offline, or the service is down - manual entry still works

    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    # `romaji` is a READBACK so the user can verify what we found. The Japanese fields stay
    # authoritative - this is a caption, never the saved value. Without it we were showing
    # 東京都江戸川区西葛西 to someone who by definition cannot read it, and asking them to
    # trust it on the single most critical field.
    romaji = " ".join(filter(None, (
        kana_to_romaji(top.get("kana1", "")),
        kana_to_romaji(top.get("kana2", "")),
        kana_to_romaji(top.get("kana3", "")),
    )))
    return {
        "prefecture": top.get("address1", ""),
        "city_ward": f"{top.get('address2', '')}{top.get('address3', '')}",
        "romaji": romaji,
    }


# ---------------------------------------------------------------------------
# MAP PIN -> OFFICIAL JAPANESE ADDRESS
# ---------------------------------------------------------------------------
# WHY THIS EXISTS, and why it is the real fix rather than the postal lookup alone.
#
# The postal code covers prefecture/city/ward. It does NOT cover WHERE you are when there is no
# postal code to hand - and it assumes the user can name their own address, which is exactly the
# assumption this project cannot make. Typing is also unreliable regardless of language: tested
# 2026-08-19, geocoding "Nishikasai 6-15-2" returned 西葛西一丁目 - the numbers were ignored
# entirely, because Japanese house-numbering is non-linear and sparsely mapped.
#
# So: POINT, DO NOT TYPE. 国土地理院 (GSI - Japan's national mapping authority) runs a free,
# keyless reverse-geocoder. Tested live on three real coordinates:
#     35.6680,139.8533 (residential) -> 西葛西二丁目
#     35.6434,139.8631 (a PARK)      -> 臨海町六丁目
#     35.7100,139.8107 (other ward)  -> 押上一丁目
# A park was tested deliberately: the founder required this to work for a school playground or
# community hall, not just a home with a postal address.
#
# This is a LOOKUP AGAINST OFFICIAL GOVERNMENT DATA, not a translation - the same principle as
# the postal lookup and the verified ontology. Nothing is machine-generated.
#
# SETUP-TIME ONLY. The result is written to profile.json and rendered to audio. During an
# emergency there is no map, no GPS and no network - the app plays a file.
#
# LIMIT: GSI resolves to 丁目, not 番地. The remaining lot and room numbers are DIGITS, which
# are identical in every language, so the user still types no Japanese.

GSI_REVERSE = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
GSI_MUNI_JS = "https://maps.gsi.go.jp/js/muni.js"

_muni_cache = {}


def _load_municipalities() -> dict:
    """GSI publishes its municipality table as a JS file: code -> '13,東京都,13123,江戸川区'."""
    if _muni_cache:
        return _muni_cache
    try:
        with urllib.request.urlopen(GSI_MUNI_JS, timeout=_TIMEOUT) as r:
            text = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return {}
    for m in re.finditer(r'GSI\.MUNI_ARRAY\["(\d+)"\]\s*=\s*[\'"]([^\'"]+)[\'"]', text):
        parts = m.group(2).split(",")
        if len(parts) >= 4:
            _muni_cache[m.group(1)] = {"prefecture": parts[1], "city_ward": parts[3]}
    return _muni_cache


def reverse_geocode(lat: float, lon: float) -> dict:
    """Coordinates -> {'prefecture', 'city_ward', 'town'} in official Japanese, or None.

    Failure is non-fatal everywhere it is used: the caller falls back to the postal code or to
    typing by hand.
    """
    try:
        url = f"{GSI_REVERSE}?lat={float(lat)}&lon={float(lon)}"
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    results = (data or {}).get("results") or {}
    muni_code, town = results.get("muniCd"), results.get("lv01Nm")
    if not muni_code or not town:
        return None

    muni = _load_municipalities().get(str(muni_code).zfill(5)) or _load_municipalities().get(str(muni_code))
    if not muni:
        return None
    return {"prefecture": muni["prefecture"], "city_ward": muni["city_ward"], "town": town}


# Free, keyless place search (OpenStreetMap's Nominatim). This is what makes the map usable
# WITHOUT Google: the user types a nearby landmark in THEIR OWN alphabet and the map jumps
# there, then they click their building.
#
# Verified 2026-08-19 that romaji input returns Japanese results:
#     "Tokyo Skytree"     -> 東京スカイツリー, 押上一丁目, 墨田区, 東京都
#     "Kasai Rinkai Park" -> 葛西臨海公園, 江戸川区, 東京都
#
# DELIBERATELY used only to MOVE THE MAP, never to fill the address directly: the same test
# showed typed street numbers are unreliable ("Nishikasai 6-15-2" -> 西葛西一丁目, numbers
# silently dropped). Search gets you to the right neighbourhood; the CLICK is what is precise.
#
# Nominatim's usage policy requires an identifying User-Agent and no more than ~1 request/sec.
# Setup-time-only, occasional use sits comfortably inside that.
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
_UA = "kyukyu-bridge/1.0 (emergency-call assistant; setup-time address lookup)"


def search_place(query: str, limit: int = 5):
    """Place name (any language) -> list of {'label', 'lat', 'lon'}.

    RETURN VALUES ARE DELIBERATELY DIFFERENT for the two failure kinds, because they need
    different messages:
        [ ... ]  found
        []       searched fine, genuinely no match  -> "try a different landmark"
        None     could NOT reach the service        -> "try again in a moment"
    Collapsing both into [] told a user with a perfectly good query to rewrite it. Observed
    live 2026-08-20: the same search that worked from a terminal returned "Nothing found" in
    the app, because Nominatim rate-limits to ~1 request/second and the failure was swallowed.
    """
    q = (query or "").strip()
    if not q:
        return []
    # accept-language ENGLISH, deliberately. These results are read by the USER choosing where
    # to put the map - they are not spoken to anyone. Returning Japanese here showed a picker
    # full of kanji to someone who by definition cannot read it. The Japanese address comes
    # from GSI when they CLICK, which is the part the dispatcher actually hears.
    params = urllib.parse.urlencode({
        "q": q, "format": "json", "accept-language": "en",
        "limit": max(1, min(int(limit), 10)), "countrycodes": "jp",
    })
    req = urllib.request.Request(f"{NOMINATIM_SEARCH}?{params}", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return None  # unreachable / rate-limited - NOT the same as "no such place"
    out = []
    for item in data or []:
        try:
            out.append({
                "label": item.get("display_name", ""),
                "lat": float(item["lat"]), "lon": float(item["lon"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# KANA -> ROMAJI, so a non-Japanese speaker can CHECK what we looked up
# ---------------------------------------------------------------------------
# THE PROBLEM THIS FIXES: the postal lookup answered 東京都江戸川区西葛西 - correct, and
# completely unverifiable by the person it was shown to. The whole product exists because the
# user does not read Japanese, so confirming an address in kanji asks the impossible. They were
# being told to trust it blindly, on the single most critical field.
#
# The postal API already returns KANA readings (ﾄｳｷｮｳﾄ / ｴﾄﾞｶﾞﾜｸ / ﾆｼｶｻｲ), which romanise
# deterministically - no translation, no model, no guessing. Purely a script conversion.
#
# FOR VERIFICATION ONLY. Long vowels are simplified the way place names are conventionally
# written (トウキョウ -> "Tokyo", not "Toukyou") because the goal is RECOGNITION by someone who
# knows their own address, not transliteration scholarship. The Japanese text remains the
# authoritative value that is saved and spoken; this is a caption.

_KANA2 = {  # two-kana combinations must be tried FIRST (キョ is "kyo", not "ki"+"yo")
    "キャ": "kya", "キュ": "kyu", "キョ": "kyo", "シャ": "sha", "シュ": "shu", "ショ": "sho",
    "チャ": "cha", "チュ": "chu", "チョ": "cho", "ニャ": "nya", "ニュ": "nyu", "ニョ": "nyo",
    "ヒャ": "hya", "ヒュ": "hyu", "ヒョ": "hyo", "ミャ": "mya", "ミュ": "myu", "ミョ": "myo",
    "リャ": "rya", "リュ": "ryu", "リョ": "ryo", "ギャ": "gya", "ギュ": "gyu", "ギョ": "gyo",
    "ジャ": "ja", "ジュ": "ju", "ジョ": "jo", "ビャ": "bya", "ビュ": "byu", "ビョ": "byo",
    "ピャ": "pya", "ピュ": "pyu", "ピョ": "pyo", "ヂャ": "ja", "ヂュ": "ju", "ヂョ": "jo",
}
_KANA1 = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヲ": "o", "ン": "n",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o",
    "ャ": "ya", "ュ": "yu", "ョ": "yo", "ー": "", "・": " ",
}


_KANJI = re.compile(r"[\u4e00-\u9fff]")


def kana_to_romaji(kana: str) -> str:
    """Katakana (half- or full-width) -> readable romaji. Deterministic; never a translation.

    Returns "" for anything containing KANJI. Kanji readings are not derivable without a
    dictionary (西葛西 could be many things), so this function must not pretend: it converts
    kana or it returns nothing. Caught 2026-08-21 when GSI's reverse geocoder was found to
    return kanji town names - passing them through unchanged would have shown 西葛西二丁目
    captioned "Reads as:", which is worse than showing no caption at all.
    """
    if not kana or _KANJI.search(kana):
        return ""
    # NFKC folds half-width katakana AND its separate voiced marks into full-width forms,
    # so ﾄﾞ (2 chars) becomes ド (1 char) before we look anything up.
    text = unicodedata.normalize("NFKC", kana)
    out, i = [], 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in _KANA2:
            out.append(_KANA2[pair]); i += 2; continue
        ch = text[i]
        if ch == "ッ":  # small tsu doubles the NEXT consonant
            nxt = text[i + 1:i + 3]
            r = _KANA2.get(nxt) or _KANA1.get(text[i + 1:i + 2], "")
            if r:
                out.append(r[0])
            i += 1; continue
        out.append(_KANA1.get(ch, ch)); i += 1
    romaji = "".join(out)
    # Conventional place-name simplification: Toukyou -> Tokyo, Yuubin -> Yubin.
    for long, short in (("ou", "o"), ("uu", "u"), ("oo", "o"), ("ee", "e")):
        romaji = romaji.replace(long, short)
    return romaji.capitalize()


NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"


def building_name_at(lat: float, lon: float) -> str:
    """Japanese name of the building at these coordinates, or "" if unknown.

    WHY A LOOKUP AND NOT A TRANSLATION: the building name is spoken to the dispatcher, so a
    guess is not acceptable. OSM has real Japanese names for many buildings (verified: the
    Skytree returns 東京スカイツリー), and where it does, that name is authoritative in the same
    way GSI's town names are.

    Coverage for ordinary apartment blocks is patchy - "" is the common answer, and the field
    stays optional. Address + room finds someone without it.
    """
    params = urllib.parse.urlencode({
        "lat": float(lat), "lon": float(lon), "format": "json",
        "accept-language": "ja", "zoom": 18, "addressdetails": 1,
    })
    req = urllib.request.Request(f"{NOMINATIM_REVERSE}?{params}", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""
    name = (data or {}).get("name") or ""
    # Reject anything that is just the町丁目 we already have, or a bare number.
    if not name or _KANJI.search(name) is None and name.isdigit():
        return ""
    return name if not re.fullmatch(r"[0-9０-９\-−]+", name) else ""


def romaji_address_at(lat: float, lon: float) -> str:
    """English/romaji READBACK for a coordinate, or "" if none is available.

    WHY THIS EXISTS: GSI returns kanji only, and kana_to_romaji() cannot help - it converts
    KANA, and returns "" the moment it meets a kanji, which every Japanese place name is made
    of. So the map path had no readback at all: it showed the user 東京都江東区南砂四丁目 and
    asked them to confirm the single most critical field in the app on faith. The postal-code
    path had a readback; the map path silently did not.

    Nominatim will answer the same coordinate in English (accept-language=en), using OSM's
    name:en tags and transliteration. That is a SECOND LOOKUP, not a translation of GSI's
    answer - the two are independent, and GSI stays authoritative for what is stored and
    spoken. This string is shown and then thrown away; it never reaches the briefing.

    Returns "" rather than a half-Japanese string: a readback the user still cannot read is
    worse than none, because it looks like confirmation.
    """
    params = urllib.parse.urlencode({
        "lat": float(lat), "lon": float(lon), "format": "json",
        "accept-language": "en", "zoom": 18, "addressdetails": 1,
    })
    req = urllib.request.Request(f"{NOMINATIM_REVERSE}?{params}", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""

    # \u3000 is the IDEOGRAPHIC space - Nominatim leaves it inside romanised names
    # ("Minami suna\u30002"), where it renders as a strange double-width gap. It is whitespace,
    # so the _JAPANESE check below does not catch it.
    raw = ((data or {}).get("display_name") or "").replace("\u3000", " ")
    parts = [re.sub(r"\s+", " ", p).strip() for p in raw.split(",")]
    keep = []
    for part in parts:
        if not part or part == "Japan":
            continue
        if re.fullmatch(r"[0-9\-\u2212]+", part):   # postcode / bare lot numbers
            continue
        if _JAPANESE.search(part):        # no name:en for this component - drop it, see above
            continue
        if part not in keep:
            keep.append(part)
    # Nominatim orders finest-first, which already reads naturally in English.
    return ", ".join(keep[:4])
