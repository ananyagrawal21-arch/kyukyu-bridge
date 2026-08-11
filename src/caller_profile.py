import json
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "profile.json"

REQUIRED_KEYS = ("address", "patient", "caller")


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
