import argparse

from ontology import load_ontology, match_all
from briefing_template import render_briefing, render_briefing_chunks, render_handoff
from caller_profile import load_profile


from stt import WHISPER_SAMPLE_RATE, prepare_audio, transcribe  # noqa: F401


def transcribe_audio(audio_path: str, language: str = None) -> str:
    """Kept for the CLI; the real implementation lives in stt.py (single source of truth)."""
    return transcribe(audio_path, language=language)


def _briefing_kwargs(
    situation_entries: list,
    extra_statements: list,
    profile: dict,
    ontology: dict,
    patient_is_profiled: bool,
    at_registered_address: bool,
) -> dict:
    """Shared prep for the briefing (string or chunked form)."""
    # Keep each term paired with its frame so the briefing phrases it correctly
    # (reported -> "says X", observed -> stated plainly).
    statements = [{"term": e["japanese_term"], "frame": e["frame"]} for e in situation_entries]
    statements += extra_statements

    # Age, sex and conditions describe one specific person. If the call is about somebody
    # else, leaving them out is safer than getting them wrong.
    if patient_is_profiled:
        patient_details = dict(
            age=profile["patient"]["age"],
            # None when sex is unknown/unrecognised, NOT 不明. Speaking 「25歳の不明です」
            # announces a field we do not have; the templates drop the word entirely instead,
            # same omit-rather-than-guess rule as the address and patient identity.
            # ONLY male/female map to a word. Anything else - "unknown", or a value that is
            # not in the map at all - becomes None, and the templates then say the age alone.
            # sex_terms DOES contain unknown->不明, so looking it up would produce
            # 「25歳の不明です」: announcing a field we do not have, which is exactly what the
            # omit-rather-than-guess rule forbids everywhere else.
            sex_ja=(
                ontology["sex_terms"].get(profile["patient"].get("sex"))
                if profile["patient"].get("sex") in ("male", "female") else None
            ),
            conditions_ja=profile["patient"].get("known_conditions", []),
            name=profile["patient"].get("name") or None,
        )
    else:
        patient_details = {}

    # Only assert the registered address if the caller confirmed they are there.
    address = _format_address(profile["address"]) if at_registered_address else None
    # The caller's own name is independent of which patient this call is about.
    caller_name = profile["caller"].get("name") or None
    return dict(address=address, statements=statements, caller_name=caller_name, **patient_details)


def build_briefing(*args) -> str:
    """The whole Japanese briefing as one string."""
    return render_briefing(**_briefing_kwargs(*args))


def build_briefing_chunks(*args) -> list:
    """The briefing as ordered, labelled chunks for paced, one-at-a-time delivery."""
    return render_briefing_chunks(**_briefing_kwargs(*args))


def build_handoff(*args) -> list:
    """Crew-facing summary rows, from the same confirmed data as the briefing.
    Address and the location state are irrelevant here - the crew has already arrived."""
    kw = _briefing_kwargs(*args)
    for drop in ("address", "caller_name", "caller_description"):
        kw.pop(drop, None)
    return render_handoff(**kw)


def _format_address(address: dict) -> str:
    return f"{address['prefecture']}{address['city_ward']}{address['street_block']} {address['building']} {address['room']}号室"


def confirm(transcript: str) -> bool:
    print(f"\nYou said: \"{transcript}\"")
    answer = input("Correct? [y/n]: ").strip().lower()
    return answer == "y"


def confirm_patient(profile: dict) -> bool:
    """Check the saved patient details actually describe the person in trouble."""
    patient = profile["patient"]
    description = f"{patient['age']}-year-old {patient.get('sex', 'unknown')}"
    conditions = patient.get("known_conditions")
    if conditions:
        description += f", known conditions: {', '.join(conditions)}"
    print(f"\nIs the emergency about: {description}?")
    answer = input("[y/n]: ").strip().lower()
    return answer == "y"


def _humanize(entry_id: str) -> str:
    return entry_id.replace("_", " ")


def confirm_interpretation(situation_entries: list, ontology: dict) -> list:
    """Show the caller WHAT WE UNDERSTOOD (not just what we heard) and let them correct it.
    Catches the SLM/matcher's two failure modes: remove a fabrication, add a missed symptom.
    This is the second confirmation loop - vetting interpretation, not transcription."""
    all_entries = [
        e for section in ("consciousness_states", "symptoms", "events")
        for e in ontology[section]
    ]
    current = list(situation_entries)

    while True:
        print("\nWe understood the following:")
        if current:
            for i, e in enumerate(current, 1):
                print(f"  {i}. {_humanize(e['id'])}")
        else:
            print("  (nothing)")
        answer = input("Enter = confirm  |  a number = remove it  |  'add' = add a symptom: ").strip().lower()

        if answer == "":
            return current
        if answer == "add":
            current_ids = {e["id"] for e in current}
            options = [e for e in all_entries if e["id"] not in current_ids]
            for i, e in enumerate(options, 1):
                print(f"  {i}. {_humanize(e['id'])}")
            pick = input("Number to add (Enter to cancel): ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(options):
                current.append(options[int(pick) - 1])
        elif answer.isdigit() and 1 <= int(answer) <= len(current):
            current.pop(int(answer) - 1)
        else:
            print("  (didn't catch that - try again)")


def confirm_location(profile: dict) -> bool:
    """Location is the most critical field. Only state the registered address if the
    caller confirms the emergency is happening there."""
    address = _format_address(profile["address"])
    print(f"\nIs the emergency at your registered address: {address}?")
    answer = input("[y/n]: ").strip().lower()
    if answer != "y":
        print("You will need to tell the dispatcher your current location.")
    return answer == "y"


def _find_entry(ontology: dict, entry_id: str) -> dict:
    for section in ("consciousness_states", "symptoms", "events"):
        for entry in ontology[section]:
            if entry["id"] == entry_id:
                return entry
    return None


def _statement_from(ontology: dict, entry_id: str) -> dict:
    entry = _find_entry(ontology, entry_id)
    return {"term": entry["japanese_term"], "frame": entry["frame"]}


def slm_matches(transcript: str, ontology: dict) -> dict:
    """Run the SLM brain and return a matches-dict (same shape as match_all), so it drops
    straight in. The SLM never returns the critical binary statuses (conscious/unconscious/
    not_breathing) - those come from ask_critical_fields."""
    from slm_classify import classify

    section_of = {
        e["id"]: section
        for section in ("consciousness_states", "symptoms", "events")
        for e in ontology[section]
    }
    key = {"consciousness_states": "consciousness", "symptoms": "symptoms", "events": "events"}
    buckets = {"consciousness": [], "symptoms": [], "events": []}
    for eid in classify(transcript, ontology):
        section = section_of.get(eid)
        if section:
            buckets[key[section]].append(_find_entry(ontology, eid))
    return buckets


def ask_critical_fields(matches: dict, ontology: dict) -> list:
    """Breathing and consciousness drive dispatch priority and CPR. If the caller
    never mentioned them, ask - one plain question each. 'Unknown' adds nothing;
    we never invent a status that wasn't given."""
    extra = []

    # Check the BINARY status specifically (not just any consciousness entry like "confused"),
    # so we still ask when only "confused" matched, and always ask under the SLM (which never
    # returns conscious/unconscious).
    binary_known = any(m["id"] in {"conscious", "unconscious"} for m in matches["consciousness"])
    if not binary_known:
        answer = input("\nIs the person awake and responsive? [y/n/unknown]: ").strip().lower()
        if answer == "y":
            extra.append(_statement_from(ontology, "conscious"))
        elif answer == "n":
            extra.append(_statement_from(ontology, "unconscious"))

    breathing_ids = {"difficulty_breathing", "not_breathing"}
    breathing_mentioned = any(m["id"] in breathing_ids for m in matches["symptoms"])
    if not breathing_mentioned:
        answer = input("Is the person breathing? [y/n/unknown]: ").strip().lower()
        if answer == "n":
            extra.append(_statement_from(ontology, "not_breathing"))
        # "y" (breathing normally) and "unknown" add nothing - there is no
        # ontology term for normal breathing, and we do not fabricate.

    return extra


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="Skip STT, use this transcript directly (for testing the ontology/template wiring)")
    parser.add_argument("--audio", help="Path to an audio file to transcribe with Whisper")
    parser.add_argument("--no-interp", action="store_true", help="Skip the interpretation-confirmation step (for measuring the flow without it)")
    parser.add_argument("--slm", action="store_true", help="Use the SLM brain instead of the crude keyword matcher")
    args = parser.parse_args()

    if args.text:
        transcript = args.text
    elif args.audio:
        transcript = transcribe_audio(args.audio)
    else:
        parser.error("Provide --text for a quick test or --audio for a real recording")
        return

    if not confirm(transcript):
        print("Please try again.")
        return

    profile = load_profile()
    ontology = load_ontology()
    if args.slm:
        print("(using the SLM brain - this takes a few seconds)")
        matches = slm_matches(transcript, ontology)
    else:
        matches = match_all(transcript, ontology)

    # Flatten the classified situations; let the caller vet our interpretation.
    situation_entries = matches["symptoms"] + matches["events"] + matches["consciousness"]
    if not args.no_interp:
        situation_entries = confirm_interpretation(situation_entries, ontology)

    extra_statements = ask_critical_fields(matches, ontology)
    at_registered_address = confirm_location(profile)
    patient_is_profiled = confirm_patient(profile)
    briefing = build_briefing(
        situation_entries,
        extra_statements,
        profile,
        ontology,
        patient_is_profiled,
        at_registered_address,
    )

    print("\n--- Structured Japanese briefing ---")
    print(briefing)
    if not patient_is_profiled:
        print("(Patient details omitted - the dispatcher will ask.)")

if __name__ == "__main__":
    main()
