"""Pre-render every Japanese sentence this app can speak, into data/audio/.

    python tools/build_audio.py            # build what's missing
    python tools/build_audio.py --force    # re-render everything

WHY THIS EXISTS
    At runtime the app must never depend on the machine having a Japanese voice. macOS has
    Kyoko; Windows needs a language pack that may simply not be installed, in which case the
    app has NO speech at all - and speech is the delivery path, not a nicety.

    We can dodge this entirely because every sentence is knowable in advance:
      - fixed lines are constants
      - the 29 ontology terms are a CLOSED set (the same property the safety design rests on)
      - profile lines (address, age, conditions) are settled when the profile is written
    So: render once here with the best voice available, ship the WAVs, play files at runtime.

RUN THIS AGAIN whenever data/profile.json or the ontology changes. Filenames are content
hashes, so edited wording just misses the cache and is re-rendered - stale audio cannot
silently outlive the text it belongs to.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import briefing_template as T  # noqa: E402
from briefing_template import _format_statement  # noqa: E402
from caller_profile import load_profile  # noqa: E402
from ontology import load_ontology  # noqa: E402
from speak import (  # noqa: E402
    AUDIO_DIR, PROFILE_AUDIO_DIR, cache_path, split_sentences, synthesize,
)


def every_sentence() -> tuple:
    """(shared, profile_specific). Sentences, not chunks: a chunk combining several symptoms is
    played by concatenating its sentences, so we never enumerate the combinations.

    The split is a PRIVACY boundary - profile lines speak a real address aloud and must not be
    committed. See PROFILE_AUDIO_DIR in speak.py."""
    ont = load_ontology()
    texts = [
        T.TEMPLATE_HEAD,
        T.TEMPLATE_LOCATION_UNKNOWN,
        T.TEMPLATE_TAIL,
        T.HANDOFF_CALLER,
        T.NO_CONDITIONS,
    ]

    # Every ontology term, in every form it can be spoken: its frame wrapper applied, plus any
    # aspect variant (vomiting/seizure/bleeding/choking can be ongoing OR finished).
    for section in ("consciousness_states", "symptoms", "events"):
        for e in ont[section]:
            for term in (e["japanese_term"], *(e.get("forms") or {}).values()):
                texts.append(_format_statement(term, e.get("frame", "observed")) + "。")

    # Profile-derived lines. Known at setup time, which is exactly why this works at all.
    personal = []
    try:
        profile = load_profile()
    except (FileNotFoundError, ValueError) as exc:
        print(f"  ! skipping profile lines: {exc}")
        return texts, personal

    for piece in T.render_location_pieces(profile["address"]):
        personal.append(piece["jp"])

    p = profile["patient"]
    age, sex_ja = p.get("age"), ont["sex_terms"].get(p.get("sex", "unknown"), "不明")
    if age is not None:
        personal.append(T.TEMPLATE_PATIENT.format(age=age, sex=sex_ja))
        if p.get("name"):
            personal.append(T.TEMPLATE_PATIENT_NAMED.format(name=p["name"], age=age, sex=sex_ja))
    conds = p.get("known_conditions") or []
    if conds:
        personal.append(T.TEMPLATE_CONDITIONS.format(conditions="、".join(conds)))
    if (profile.get("caller") or {}).get("name"):
        personal.append(T.TEMPLATE_CALLER_NAME.format(name=profile["caller"]["name"]))

    return texts, personal


def _flatten(texts) -> list:
    """Split into sentences and de-duplicate, preserving order. Several templates share
    sentences (救急です。 opens both the head constant and the location pieces)."""
    out = []
    for text in texts:
        for s in split_sentences(text):
            if s not in out:
                out.append(s)
    return out


def main():
    force = "--force" in sys.argv
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    shared_texts, personal_texts = every_sentence()
    shared = _flatten(shared_texts)
    personal = [s for s in _flatten(personal_texts) if s not in shared]

    print(f"{len(shared)} shared + {len(personal)} profile-specific sentences")
    built = skipped = failed = 0
    for sentences, is_profile in ((shared, False), (personal, True)):
        for s in sentences:
            path = cache_path(s, profile_specific=is_profile)
            if path.exists() and not force:
                skipped += 1
                continue
            audio = synthesize(s)
            if not audio:
                print(f"  FAILED  {s}")
                failed += 1
                continue
            path.write_bytes(audio)
            built += 1
            print(f"  built   {'profile/' if is_profile else '        '}{path.name}  {s}")

    print(f"\nbuilt {built}, already present {skipped}, failed {failed}")
    if failed:
        print("Failures mean no working TTS on THIS machine - run the build somewhere with a "
              "Japanese voice, then commit data/audio/.")
        sys.exit(1)


if __name__ == "__main__":
    main()
