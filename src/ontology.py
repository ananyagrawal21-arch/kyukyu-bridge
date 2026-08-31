import json
import re
from pathlib import Path

ONTOLOGY_PATH = Path(__file__).resolve().parent.parent / "data" / "ontology.json"


def load_ontology(path: Path = ONTOLOGY_PATH) -> dict:
    # encoding="utf-8" is required, not optional: this file is full of Japanese text, and
    # Windows' default text encoding (cp1252) cannot represent it - read_text() without this
    # crashes with UnicodeDecodeError on Windows while working by accident on Mac/Linux.
    return json.loads(path.read_text(encoding="utf-8"))


def _phrase_in(phrase: str, text: str) -> bool:
    # Whole-word match, so "conscious" does not fire inside "unconscious".
    # Still a crude Week-1 placeholder - the SLM replaces this with meaning-based matching.
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def find_matches(transcript: str, entries: list[dict]) -> list[dict]:
    text = transcript.lower()
    return [e for e in entries if any(_phrase_in(p, text) for p in e["trigger_phrases_en"])]


def match_all(transcript: str, ontology: dict) -> dict:
    return {
        "consciousness": find_matches(transcript, ontology["consciousness_states"]),
        "symptoms": find_matches(transcript, ontology["symptoms"]),
        "events": find_matches(transcript, ontology["events"]),
    }
