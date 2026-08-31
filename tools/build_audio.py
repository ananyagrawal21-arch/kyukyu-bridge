"""Pre-render every Japanese sentence this app can speak, into data/audio/.

    python tools/build_audio.py            # build what's missing
    python tools/build_audio.py --force    # re-render everything

WHY THIS EXISTS
    At runtime the app must never depend on the machine having a Japanese voice. macOS has
    Kyoko; Windows needs a language pack that may simply not be installed, in which case the
    app has NO speech at all - and speech is the delivery path, not a nicety.

    We can dodge this entirely because every sentence is knowable in advance:
      - fixed lines are constants
      - the ontology terms are a CLOSED set (the same property the safety design rests on)
      - profile lines (address, age, conditions) are settled when the profile is written
    So: render once here with the best voice available, ship the WAVs, play files at runtime.

RUN THIS AGAIN whenever data/profile.json or the ontology changes. Filenames are content
hashes, so edited wording just misses the cache and is re-rendered - stale audio cannot
silently outlive the text it belongs to.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import briefing_template as T  # noqa: E402
from briefing_template import _format_statement  # noqa: E402
from caller_profile import load_profile  # noqa: E402
from ontology import load_ontology  # noqa: E402
from speak import (  # noqa: E402
    AUDIO_DIR, PROFILE_AUDIO_DIR, cache_path, current_voice, split_sentences, synthesize,
)

# Records WHICH VOICE rendered the cache. Without it the cache is invisible to voice changes:
# filenames hash the TEXT only, so installing a better voice (Kyoko -> Kyoko (Enhanced)) leaves
# every existing WAV in place forever and the app keeps playing the worse one. That is exactly
# what happened between 2026-08-17 and 2026-08-22 - the audio was base Kyoko, whose Japanese
# pitch accent is noticeably wrong, long after the Enhanced voice was available.
BUILD_INFO = AUDIO_DIR / "BUILD_INFO.json"


def every_sentence() -> tuple:
    """(shared, profile_specific). Sentences, not chunks: a chunk combining several symptoms is
    played by concatenating its sentences, so we never enumerate the combinations.

    The split is a PRIVACY boundary - profile lines speak a real address aloud and must not be
    committed. See PROFILE_AUDIO_DIR in speak.py."""
    ont = load_ontology()
    texts = [
        T.TEMPLATE_HEAD,
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

    # ALSO the COMBINED location sentence. render_location_pieces splits the address into
    # separate play buttons for the dispatch_now screen, but render_briefing_chunks builds it as
    # ONE sentence (場所は<whole address>です。) for the briefing's chunk 0. The briefing normally
    # opens at chunk 1 - chunk 0 was already delivered - but "Previous part" can reach it, and
    # without this it was the only chunk in the app that fell back to live synthesis.
    from pipeline import build_briefing_chunks  # local: avoids a circular import at module load
    personal.append(build_briefing_chunks([], [], profile, ont, True, True)[0]["jp"])

    p = profile["patient"]
    # MUST mirror _briefing_kwargs in pipeline.py exactly. It used to default to 不明 here while
    # the briefing had moved to omitting sex entirely - so this rendered 「25歳の不明です」 while
    # the app asked for 「25歳です」, a guaranteed cache MISS that silently dropped the app back
    # to live synthesis: the machine-dependent path pre-rendering exists to eliminate.
    age = p.get("age")
    sex_ja = ont["sex_terms"].get(p.get("sex")) if p.get("sex") in ("male", "female") else None
    if age is not None:
        if sex_ja:
            personal.append(T.TEMPLATE_PATIENT.format(age=age, sex=sex_ja))
            if p.get("name"):
                personal.append(
                    T.TEMPLATE_PATIENT_NAMED.format(name=p["name"], age=age, sex=sex_ja))
        else:
            personal.append(T.TEMPLATE_PATIENT_NO_SEX.format(age=age))
            if p.get("name"):
                personal.append(T.TEMPLATE_PATIENT_NAMED_NO_SEX.format(name=p["name"], age=age))
    conds = p.get("known_conditions") or []
    if conds:
        personal.append(T.TEMPLATE_CONDITIONS.format(conditions="、".join(conds)))
    if (profile.get("caller") or {}).get("name"):
        personal.append(T.TEMPLATE_CALLER_NAME.format(name=profile["caller"]["name"]))

    return texts, personal


def _lock_down(path: Path):
    """Owner-only. These recordings say a home address out loud; the default lets every
    account on the machine read them."""
    try:
        path.chmod(0o600)
    except OSError:
        pass  # non-POSIX filesystem; the gitignore boundary still holds


def _flatten(texts) -> list:
    """Split into sentences and de-duplicate, preserving order. Several templates share
    sentences (救急です。 opens both the head constant and the location pieces)."""
    out = []
    for text in texts:
        for s in split_sentences(text):
            if s not in out:
                out.append(s)
    return out


def build(force: bool = False, log=print) -> dict:
    """Render missing audio and REMOVE personal audio that is no longer needed.

    Callable from the app's setup screen, not just the command line.

    The removal step matters for privacy: without it, changing your address leaves the old
    address's recording on disk forever, and the folder slowly accumulates a spoken history of
    every address and medical condition ever entered.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # A voice change invalidates EVERYTHING, because every file was rendered by the old one.
    voice = current_voice()
    previous = None
    if BUILD_INFO.exists():
        try:
            previous = json.loads(BUILD_INFO.read_text(encoding="utf-8")).get("voice")
        except (ValueError, OSError):
            previous = None
    if previous != voice:
        if previous is not None:
            log(f"  voice changed: {previous} -> {voice}; rebuilding everything")
        force = True

    shared_texts, personal_texts = every_sentence()
    shared = _flatten(shared_texts)
    personal = [s for s in _flatten(personal_texts) if s not in shared]

    built = skipped = failed = 0
    for sentences, is_profile in ((shared, False), (personal, True)):
        for s in sentences:
            path = cache_path(s, profile_specific=is_profile)
            if path.exists() and not force:
                skipped += 1
                continue
            audio = synthesize(s)
            if not audio:
                log(f"  FAILED  {s}")
                failed += 1
                continue
            path.write_bytes(audio)
            _lock_down(path)
            built += 1
            log(f"  built   {'profile/' if is_profile else '        '}{path.name}  {s}")

    # Anything in the personal folder that the CURRENT profile does not need is stale.
    wanted = {cache_path(s, profile_specific=True).name for s in personal}
    removed = 0
    for old in PROFILE_AUDIO_DIR.glob("*.wav"):
        if old.name not in wanted:
            old.unlink()
            removed += 1
            log(f"  removed stale profile/{old.name}")
        else:
            _lock_down(old)  # every run, not just newly built - files made before this
                             # existed are still world-readable otherwise

    if not failed:
        BUILD_INFO.write_text(json.dumps({"voice": voice}, indent=2), encoding="utf-8")

    return {"built": built, "skipped": skipped, "failed": failed, "removed": removed}


def main():
    result = build(force="--force" in sys.argv)
    built, skipped = result["built"], result["skipped"]
    failed, removed = result["failed"], result["removed"]
    print(f"\nbuilt {built}, already present {skipped}, removed {removed}, failed {failed}")
    if failed:
        print("Failures mean no working TTS on THIS machine - run the build somewhere with a "
              "Japanese voice, then commit data/audio/.")
        sys.exit(1)


if __name__ == "__main__":
    main()
