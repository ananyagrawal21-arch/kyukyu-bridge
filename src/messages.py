"""Build the payloads that go from the caller's phone to the console (PROTOCOL.md section 3).

The app already holds everything the console needs - the profile, and the confirmed statements
built by pipeline._statement_from. This file only reshapes them. It also enforces the project's
core safety property in code, not by convention: a situation item whose Japanese did not come
verbatim out of data/ontology.json is refused, so the model can never put its own Japanese on a
dispatcher's screen even if something upstream is wrong.
"""
from briefing_template import CPA_IDS

SECTIONS = ("consciousness_states", "symptoms", "events")
SECTION_NAME = {"consciousness_states": "consciousness", "symptoms": "symptom", "events": "event"}
SOURCES = {"slm", "caller_added", "forced_question", "dispatcher_answer"}


def _index(ontology: dict) -> dict:
    return {e["id"]: (section, e) for section in SECTIONS for e in ontology[section]}


def _gloss(entry_id: str) -> str:
    return entry_id.replace("_", " ")


def profile_payload(profile: dict, ontology: dict, *, address_confirmed=True,
                    patient_is_profiled=True) -> dict:
    """PROTOCOL.md 3.1. Address keys are passed through unchanged, so nothing is renamed on the way."""
    patient = profile.get("patient") or {}
    sex = patient.get("sex") or "unknown"
    by_term = {c["japanese_term"]: c for c in ontology["conditions"]}

    conditions = []
    for term in patient.get("known_conditions") or []:
        c = by_term.get(term)
        # A condition the ontology does not list is still a real diagnosis - it is sent, but with
        # id None and verified False, so the console shows it in the separate "not verified" block
        # (PROTOCOL.md open question 4).
        conditions.append({
            "id": c["id"] if c else None,
            "ja": term,
            "en": c.get("label_en") if c else None,
            "verified": bool(c and c.get("verified")),
        })

    caller = profile.get("caller") or {}
    return {
        "address": dict(profile.get("address") or {}),
        "address_confirmed": address_confirmed,
        "patient_is_profiled": patient_is_profiled,
        "patient": {
            "name": patient.get("name"),
            "age": patient.get("age"),
            "sex": sex,
            "sex_ja": ontology["sex_terms"].get(sex),
            "known_conditions": conditions,
        },
        "caller": {
            "name": caller.get("name"),
            "native_language": caller.get("native_language"),
            "japanese_fluency": caller.get("japanese_fluency"),
        },
        "profile_updated_at": profile.get("updated_at"),
    }


def situation_item(statement: dict, ontology: dict, *, source: str = "slm",
                   confirmed: bool = True) -> dict:
    """One item for PROTOCOL.md 3.2, from a statement {"id", "term", "frame"}.

    Raises ValueError if the statement's Japanese is not one of the ontology's own forms for
    that id. This is the provenance check: it is the last point before the console.
    """
    if source not in SOURCES:
        raise ValueError(f"unknown source {source}")
    found = _index(ontology).get(statement.get("id"))
    if found is None:
        raise ValueError(f"id {statement.get('id')!r} is not in the ontology")
    section, entry = found

    ongoing = entry["japanese_term"]
    finished = (entry.get("forms") or {}).get("finished")
    ja = statement["term"]
    if ja == ongoing:
        aspect = "ongoing" if finished else None
    elif finished and ja == finished:
        aspect = "finished"
    else:
        raise ValueError(f"Japanese for {entry['id']!r} is not from the ontology: {ja!r}")

    return {
        "id": entry["id"],
        "section": SECTION_NAME[section],
        "ja": ja,
        "en": _gloss(entry["id"]),
        "frame": statement.get("frame", entry.get("frame")),
        "aspect": aspect,
        "critical": bool(entry.get("critical")) or entry["id"] in CPA_IDS,
        "verified": bool(entry.get("verified")),
        "source": source,
        "confirmed": confirmed,
    }


def situation_payload(statements: list, ontology: dict, *, revision: int = 1,
                      supersedes: str = None, sources: dict = None) -> dict:
    """PROTOCOL.md 3.2: the full situation, re-sent whole on every change (open question 2).

    `sources` maps id -> source for items that did not come from the model (e.g. the forced
    breathing question). Anything not listed is recorded as "slm".
    """
    sources = sources or {}
    items = [situation_item(s, ontology, source=sources.get(s.get("id"), "slm"))
             for s in statements]
    # Critical first, so a console that renders in order cannot bury "not breathing".
    items.sort(key=lambda i: not i["critical"])
    return {"revision": revision, "supersedes": supersedes, "items": items}
