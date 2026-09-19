"""E1b-E4, one change per run, all scored through harness.py.

Nothing here edits src/. Each variant is a function swapped in for the run and dropped after.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H                      # noqa: E402
import slm_classify as SC                # noqa: E402
from ontology import load_ontology       # noqa: E402

ONT = load_ontology()
TRIGGERS = {e["id"]: e["trigger_phrases_en"]
            for s in ("consciousness_states", "symptoms", "events") for e in ONT[s]}

# ---------------------------------------------------------------- E1b: looser glosses
# E1's glosses were terse and clinical ("pain in the head") with contrastive NOT clauses, and
# they made Stage B DELETE things it used to keep: headache, vomiting, cold_sweat. These are
# written in the register the existing 15 use - everyday synonyms, no contrast, no emphasis.
# no_pulse stays narrow ON PURPOSE: it is the one id where over-deleting is the safe direction.
GLOSSES_V2 = {
    "conscious": "awake and responding",
    "unconscious": "not awake, not responding",
    "not_breathing": "not breathing",
    "cold_sweat": "sweating, clammy, or in a cold sweat",
    "pale_complexion": "pale, grey, or washed-out looking",
    "headache": "a headache, or the head hurting or pounding",
    "palpitations": "the heart racing, pounding, or fluttering",
    "back_pain": "pain in the back",
    "lower_back_pain": "pain in the lower back or around the waist",
    "dizziness": "dizzy, light-headed, or the room spinning",
    "vomiting": "vomiting, throwing up, or being sick",
    "nausea": "feeling sick or queasy",
    "numbness": "numbness, tingling, or pins and needles",
    "no_pulse": "the statement says no pulse or no heartbeat can be felt - not merely that the "
                "person is unresponsive, still, or collapsed",
    "body_cold": "the body or skin feels cold",
    "drowning": "went under water, or was pulled from water",
}


def with_glosses_v2(pipe, transcript, candidate_ids):
    original = dict(SC.DESCRIPTIONS)
    SC.DESCRIPTIONS.update(GLOSSES_V2)
    try:
        return SC._review_list(pipe, transcript, candidate_ids)
    finally:
        SC.DESCRIPTIONS.clear()
        SC.DESCRIPTIONS.update(original)


# ---------------------------------------------------------------- E3: negation gate
# Matched as whole words. "no" without a trailing boundary matched "now" and "nothing", which
# vetoed `seizure` in "he collapsed and now he's convulsing" - a live seizure deleted by a typo
# in a regex. Kept as one pattern so the phrase-exemption test and the window test agree.
NEG_RE = re.compile(r"\b(?:not|no|never|without|denies|cannot)\b|n\'t\b")
# Stops the veto crossing a clause boundary: in "bleeding a lot but he did not hit his head"
# the denial belongs to the head, not to the bleeding.
# A denial stops at the clause it belongs to. Without the comma, "no fever, no vomiting, it's
# just his chest that hurts" let the denial reach `chest_pain` - the caller said the opposite.
STOPS = (" but ", " although ", " though ", " however ", ",", " and ")


def _anchors(sid):
    """Words that actually identify this id, not generic clinical filler.

    A word used by three or more different ids ("pain", "hurts", "his") identifies nothing, and
    matching on it is what let "it hurts, it really hurts" resolve to chest_pain. Computed from
    the ontology so it stays correct as the menu grows.
    """
    global _DF
    if _DF is None:
        _DF = {}
        for ids, phrases in TRIGGERS.items():
            for w in set(_WORD.findall(" ".join(phrases).lower())):
                _DF[w] = _DF.get(w, 0) + 1
    return {w for w in _WORD.findall(" ".join(TRIGGERS.get(sid, [])).lower())
            if _DF.get(w, 0) < 3 and w not in _STOP}


_DF = None
_STOP = {"his", "her", "the", "a", "is", "in", "of", "and", "to", "it", "on", "up", "at",
         "he", "she", "t", "s", "something", "lot", "lots", "cant", "wont", "there"}


def _negated_span(transcript, sid):
    """Is this id's evidence under a local denial?

    Two passes, and the order matters. A trigger phrase that CONTAINS the negation is the
    finding itself - "can't find a pulse" and "no pulse" report an arrest, and vetoing them
    would delete the most important id in the ontology on the exact words that report it. Only
    after ruling that out do we look for a denial sitting in front of the evidence.
    """
    low = transcript.lower()
    # NEGATION AS THE FINDING. "can't find a pulse", "isn't making any sense" and "not breathing"
    # report the emergency THROUGH the negation. Literal phrase matching missed these, because a
    # caller writes "isn't making any sense" where the ontology has "not making sense". Compare
    # on content words instead: if this id has a negated trigger whose other words are all
    # present, the denial belongs to the finding and nothing is vetoed.
    said = set(_WORD.findall(low))
    for phrase in TRIGGERS.get(sid, []):
        if not NEG_RE.search(phrase.lower()):
            continue
        content = {w for w in _WORD.findall(NEG_RE.sub(" ", phrase.lower())) if w not in _STOP}
        if content and content <= said:
            return False
    for word in _anchors(sid):
        for m in re.finditer(rf"\b{re.escape(word)}", low):
            window = low[max(0, m.start() - 45):m.start()]
            for stop in STOPS:                 # do not let a denial cross a clause boundary
                if stop in window:
                    window = window.rsplit(stop, 1)[1]
            if NEG_RE.search(window):
                return True
    return False


def _expressible_by_negation(sid):
    """Can this symptom be REPORTED using a negation?

    Measured 2026-09-13, and it is the whole story for this gate. English states most of these
    findings negatively: "can't breathe", "won't move", "won't stop bleeding", "can't make out
    his words", "won't wake up". Seven of nine removals on the real sets were findings of this
    kind, not denials. So if an id can be reported through a negation, a negation must never be
    allowed to delete it - the risk is entirely one-sided.
    """
    return any(NEG_RE.search(p.lower()) for p in TRIGGERS.get(sid, []))


_NEGATABLE = None


def negation_gate(transcript, ids):
    global _NEGATABLE
    if _NEGATABLE is None:
        _NEGATABLE = {i for i in TRIGGERS if _expressible_by_negation(i)}
    return {i for i in ids if i in _NEGATABLE or not _negated_span(transcript, i)}


# ---------------------------------------------------------------- E4: lexical veto
# Deliberately NOT global. V2 (quote-the-evidence, applied to everything) took misses from 3 to
# 20 because the model cannot quote for paraphrase - "brought up everything she ate" IS vomiting
# with no quotable span. These five are the ids where a false positive changes the dispatch, and
# where the wording is literal enough that zero overlap really does mean "not stated".
HIGH_COST = {"no_pulse", "chest_pain", "head_injury", "seizure", "choking"}
_WORD = re.compile(r"[a-z]+")


def _overlap(transcript, sid):
    """Does the statement contain anything that actually points at this id?

    Whole trigger phrase present, or one of the id's DISTINCTIVE anchor words. Generic words
    are excluded by _anchors, so "it hurts" no longer counts as evidence for chest_pain while
    "clutching his chest" still does.
    """
    said = set(_WORD.findall(transcript.lower()))
    for phrase in TRIGGERS.get(sid, []):
        words = set(_WORD.findall(phrase.lower())) - _STOP
        if words and words <= said:
            return True
    return bool(_anchors(sid) & said)


def lexical_veto(transcript, ids):
    return {i for i in ids if i not in HIGH_COST or _overlap(transcript, i)}


def both_gates(transcript, ids):
    return lexical_veto(transcript, negation_gate(transcript, ids))


if __name__ == "__main__":
    results = [
        H.run_variant("baseline"),
        H.run_variant("E2a no_pulse discard", discard={"no_pulse"}),
        H.run_variant("E3 negation gate", gate=negation_gate),
        H.run_variant("E4 lexical veto", gate=lexical_veto),
        H.run_variant("E3+E4", gate=both_gates),
        H.run_variant("E2a+E3+E4", gate=both_gates, discard={"no_pulse"}),
    ]
    H.report(results)
