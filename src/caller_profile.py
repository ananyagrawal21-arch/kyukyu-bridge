import json
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "profile.json"

REQUIRED_KEYS = ("address", "patient", "caller")


def romaji_fields(profile: dict) -> list:
    """Labels of every SPOKEN profile field that is romaji, so a Japanese voice cannot read it.

    Covers EVERY field that ends up in the briefing, not just the address. The first version of
    this check only looked at address fields, which missed the patient's name, their conditions
    and the caller's name - all three are spoken aloud, so "名前はYamada Hanako" and
    "持病はHeart problem" reached the dispatcher as noise exactly like the address did. Same
    bug, three more places.

    Room number is NOT checked: it is digits, which a Japanese voice reads correctly.
    """
    from postal import looks_romaji

    addr = profile.get("address") or {}
    patient = profile.get("patient") or {}
    caller = profile.get("caller") or {}
    candidates = [
        ("Prefecture", addr.get("prefecture")),
        ("City/ward", addr.get("city_ward")),
        ("Area & block number", addr.get("street_block")),
        ("Building", addr.get("building")),
        ("Patient name", patient.get("name")),
        ("Known conditions", "、".join(patient.get("known_conditions") or [])),
        ("Your name", caller.get("name")),
    ]
    return [label for label, value in candidates if looks_romaji(value)]


def load_profile(path: Path = PROFILE_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"No profile found at {path}. Copy data/profile.example.json to "
            f"data/profile.json and fill in real details."
        )
    # encoding="utf-8" required - the address fields are Japanese; Windows' default text
    # encoding cannot read them (crashes with UnicodeDecodeError, works by luck on Mac/Linux).
    profile = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in profile]
    if missing:
        raise ValueError(f"profile.json is missing required section(s): {missing}")
    return profile
