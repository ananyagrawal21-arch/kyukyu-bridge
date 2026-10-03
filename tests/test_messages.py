import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from messages import profile_payload, situation_item, situation_payload

ONTOLOGY = json.loads((ROOT / "data" / "ontology.json").read_text())
PROFILE = json.loads((ROOT / "data" / "profile.example.json").read_text())


def _stmt(entry_id, term=None):
    for section in ("consciousness_states", "symptoms", "events"):
        for e in ONTOLOGY[section]:
            if e["id"] == entry_id:
                return {"id": e["id"], "term": term or e["japanese_term"], "frame": e["frame"]}
    raise KeyError(entry_id)


def test_profile_keeps_address_keys_unchanged():
    p = profile_payload(PROFILE, ONTOLOGY)
    assert p["address"] == PROFILE["address"]
    assert p["patient"]["sex_ja"] == "女性"


def test_known_condition_maps_to_ontology_id():
    p = profile_payload(PROFILE, ONTOLOGY)
    by_ja = {c["ja"]: c for c in p["patient"]["known_conditions"]}
    assert by_ja["高血圧"]["id"] == "hypertension"


def test_unknown_condition_is_sent_but_marked_unverified():
    prof = json.loads(json.dumps(PROFILE))
    prof["patient"]["known_conditions"] = ["架空の病気"]
    c = profile_payload(prof, ONTOLOGY)["patient"]["known_conditions"][0]
    assert c == {"id": None, "ja": "架空の病気", "en": None, "verified": False}


def test_item_carries_ontology_japanese_verbatim():
    item = situation_item(_stmt("difficulty_breathing"), ONTOLOGY)
    assert item["ja"] == "息が苦しいです"
    assert item["section"] == "symptom" and item["verified"] is True


def test_japanese_not_from_ontology_is_refused():
    # The core safety property: model-written Japanese must never reach the console.
    bad = {"id": "headache", "term": "頭がすごく痛いみたいです", "frame": "observed"}
    with pytest.raises(ValueError):
        situation_item(bad, ONTOLOGY)


def test_unknown_id_is_refused():
    with pytest.raises(ValueError):
        situation_item({"id": "made_up", "term": "x", "frame": "observed"}, ONTOLOGY)


def test_finished_form_is_accepted_and_marked():
    item = situation_item(_stmt("seizure", term="けいれんしていました"), ONTOLOGY)
    assert item["aspect"] == "finished"
    assert situation_item(_stmt("seizure"), ONTOLOGY)["aspect"] == "ongoing"


def test_cpa_items_sort_first_and_are_critical():
    payload = situation_payload([_stmt("headache"), _stmt("not_breathing")], ONTOLOGY,
                                sources={"not_breathing": "forced_question"})
    first = payload["items"][0]
    assert first["id"] == "not_breathing" and first["critical"] is True
    assert first["source"] == "forced_question"
    assert payload["items"][1]["source"] == "slm"
