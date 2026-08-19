"""One-time setup: write data/profile.json and render its audio.

    python tools/setup_profile.py

This is the "pre-registration" step. NET119 - the fire agency's own caller-side app - requires
pre-registration too, so this is the accepted shape for this kind of tool, not a workaround.

It exists because the alternative is a panicking family member hand-editing JSON, and because
the profile-derived lines (address, age, conditions) must be rendered to audio BEFORE an
emergency - the whole point of pre-rendering is that no speech is synthesised during a call.

Existing values are shown in [brackets]; press Enter to keep them.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from caller_profile import PROFILE_PATH  # noqa: E402
from postal import lookup as postal_lookup, looks_romaji  # noqa: E402

SEXES = ("male", "female", "unknown")


def ask(prompt: str, current=None, required: bool = False) -> str:
    shown = f" [{current}]" if current not in (None, "") else ""
    while True:
        answer = input(f"{prompt}{shown}: ").strip()
        if not answer and current not in (None, ""):
            return str(current)
        if answer:
            return answer
        if not required:
            return ""
        print("  (required)")


def ask_choice(prompt: str, options: tuple, current=None) -> str:
    while True:
        answer = ask(f"{prompt} ({'/'.join(options)})", current, required=True)
        if answer in options:
            return answer
        print(f"  (must be one of: {', '.join(options)})")


def ask_int(prompt: str, current=None) -> int:
    while True:
        answer = ask(prompt, current, required=True)
        if answer.isdigit():
            return int(answer)
        print("  (numbers only)")


def main():
    existing = {}
    if PROFILE_PATH.exists():
        existing = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        print(f"Editing existing profile at {PROFILE_PATH}\n")
    else:
        print("Creating a new profile.\n")

    addr = existing.get("address", {})
    pat = existing.get("patient", {})
    caller = existing.get("caller", {})

    print("--- Where the ambulance should come ---")
    print("Enter your 7-digit POSTAL CODE and we look up the Japanese prefecture/city/ward for")
    print("you - you never have to type Japanese yourself. Blank to skip and type it by hand.")
    pc = ask("Postal code (e.g. 134-0088)")
    found = postal_lookup(pc) if pc else None
    if pc and not found:
        print("  Could not look that up (offline, or not a real code) - type it below by hand.")
    address = {
        "prefecture": ask(
            "Prefecture 都道府県",
            (found or {}).get("prefecture") or addr.get("prefecture"), required=True,
        ),
        "city_ward": ask(
            "City / ward 市区町村",
            (found or {}).get("city_ward") or addr.get("city_ward"), required=True,
        ),
        "street_block": ask("Street & block 丁目番地 (Japanese)", addr.get("street_block"), required=True),
        "building": ask("Building 建物名 (Japanese, blank if none)", addr.get("building")),
        "room": ask("Room 部屋番号 (blank if none)", addr.get("room")),
    }
    # The postal lookup only covers prefecture/city/ward - street_block and building are
    # still typed by hand, so the same romaji mistake remains possible there.
    romaji_fields = [
        label for label, val in (
            ("street_block", address["street_block"]), ("building", address["building"]),
        ) if looks_romaji(val)
    ]
    if romaji_fields:
        print(
            f"\n  WARNING: {', '.join(romaji_fields)} looks like romaji, not Japanese. "
            "A Japanese voice cannot read it, and the dispatcher would hear noise for the "
            "single most critical field. Please re-enter in Japanese."
        )

    print("\n--- The person most likely to need help ---")
    patient = {
        "name": ask("Name 名前 (Japanese, blank to omit)", pat.get("name")),
        "age": ask_int("Age", pat.get("age")),
        "sex": ask_choice("Sex", SEXES, pat.get("sex")),
    }
    conds = ask(
        "Known conditions 持病, comma-separated in Japanese (blank if none)",
        "、".join(pat.get("known_conditions") or []) or None,
    )
    patient["known_conditions"] = [c.strip() for c in conds.replace("、", ",").split(",") if c.strip()]

    print("\n--- You, the caller ---")
    caller_out = {
        "name": ask("Your name 名前 (Japanese, blank to omit)", caller.get("name")),
        "native_language": ask(
            "Language code you will SPEAK to the app (en/vi/zh/ko/tl/th/pt/ne/id)",
            caller.get("native_language", "en"), required=True,
        ),
        "japanese_fluency": caller.get("japanese_fluency", "limited"),
    }

    profile = {"address": address, "patient": patient, "caller": caller_out}
    PROFILE_PATH.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nSaved {PROFILE_PATH}")

    # Non-negotiable: without this the address has no audio, and the app would fall back to
    # live synthesis - which is exactly the machine-dependent path we are removing.
    print("\nRendering audio for the new details...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_audio.py")],
        capture_output=True, text=True,
    )
    print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr)
    if result.returncode != 0:
        print("\nAudio build FAILED - this machine has no Japanese voice. Run "
              "tools/build_audio.py on a machine that does, and copy data/audio/ across.")
        sys.exit(1)
    print("\nDone. Start the app with: streamlit run app.py")


if __name__ == "__main__":
    main()
