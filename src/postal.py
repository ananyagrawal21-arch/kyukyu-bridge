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
    return {
        "prefecture": top.get("address1", ""),
        "city_ward": f"{top.get('address2', '')}{top.get('address3', '')}",
    }
