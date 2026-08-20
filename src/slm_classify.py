"""
Stage 1 of the SLM: meaning-based classification.

Replaces the crude substring matcher. Given the caller's statement, the model
SELECTS which ontology situations apply - it returns situation IDs, it does NOT
generate Japanese. We look up the verified term for each ID afterwards, so this
step can never hallucinate Japanese or a diagnosis.

Plain PyTorch here (prove the flow first). OpenVINO conversion comes later.
"""
import difflib
import json
import re

from ontology import load_ontology

import os

# MUST stay 3B. 1.5B was measured UNRELIABLE - it inverted critical binary fields ("still
# awake" -> unconscious), which is the single most dangerous error this system can make.
# This default used to be 1.5B while convert_slm.py used 3B, so any machine WITHOUT a
# converted models/ directory (a fresh clone - models/ is gitignored) silently ran the
# rejected model with no warning. Keep this in step with benchmark/convert_slm.py.
MODEL_ID = os.environ.get("SLM_MODEL", "Qwen/Qwen2.5-3B-Instruct")

# Critical binary STATUS fields are never DECIDED by the SLM - a 1.5B model inverted them
# ("still awake" -> unconscious). They come from the deterministic ask_critical_fields step.
#
# BUT they stay IN THE MENU. Removing them left the concept with nowhere to go: when the
# caller said "he's not breathing", the model displaced onto the nearest available label and
# fabricated no_pulse / difficulty_breathing (4 of 5 fabrications in the 2026-08-03 eval).
# Keeping them selectable gives the concept a home; we then DISCARD the model's answer for
# them, so safety is unchanged.
SLM_DISCARD = {"conscious", "unconscious", "not_breathing"}
SLM_EXCLUDE = set()  # nothing is hidden from the menu any more

_pipe = None
_ALIAS_TIERS = None  # cached; rebuilt aliases on every parse otherwise


def _load_pipe():
    global _pipe
    if _pipe is None:
        from transformers import pipeline, AutoTokenizer
        ov_dir = os.environ.get("SLM_OV_DIR")
        if ov_dir and os.path.isdir(ov_dir):
            # OpenVINO INT8 path (the optimized/shippable one).
            from optimum.intel import OVModelForCausalLM
            # (Disk compile-cache was tried and dropped: only ~20s saved for 6 GB on this
            #  ARM Mac. The real win is the app-open warm-up keeping the model warm in RAM.
            #  Worth re-testing CACHE_DIR on Intel hardware later.)
            model = OVModelForCausalLM.from_pretrained(ov_dir)
            tok = AutoTokenizer.from_pretrained(ov_dir)
            _pipe = pipeline("text-generation", model=model, tokenizer=tok, device=-1)
        else:
            # Plain PyTorch fallback (the slow baseline). Say so loudly - silently running
            # unoptimized is how a demo machine ends up several seconds slower than the
            # measured numbers with nobody noticing why.
            print(
                f"[slm_classify] models/ not found - running {MODEL_ID} as PLAIN PYTORCH "
                f"(slow, unoptimized). Convert with benchmark/convert_slm.py for the "
                f"OpenVINO INT8 path.",
                flush=True,
            )
            _pipe = pipeline("text-generation", model=MODEL_ID, device=-1)
    return _pipe


def _situation_menu(ontology):
    """Flat list of (id, gloss) the model chooses from. Gloss = a few trigger phrases.
    Critical binary statuses (SLM_EXCLUDE) are left out - handled deterministically."""
    menu = []
    for section in ("consciousness_states", "symptoms", "events"):
        for e in ontology[section]:
            if e["id"] in SLM_EXCLUDE:  # skip only the critical binary statuses
                continue
            gloss = "; ".join(e["trigger_phrases_en"][:4])
            menu.append((e["id"], gloss))
    return menu


SYSTEM_PROMPT = (
    "You are an emergency-call intake classifier. Given a caller's statement and a "
    "list of possible situations, return the ids that are LITERALLY stated or clearly "
    "described. Rules:\n"
    "- Judge by meaning, not exact words.\n"
    "- Include a situation ONLY if the statement actually describes it. Never infer or "
    "guess. Never add related conditions that were not mentioned.\n"
    "- If unsure about one, leave it out.\n"
    "- Do not diagnose.\n"
    'Respond with ONLY a JSON array of id strings, e.g. ["chest_pain","collapsed"]. '
    "If none apply, return []."
)

# Few-shot examples teach restraint: pick what is stated, ignore what is not in the menu.
_FEWSHOT = [
    ("his chest feels really tight and he's sweating a lot", '["chest_pain"]'),
    # Deliberately a TRIP, answered with `fall` not `collapsed` - this example is doing double
    # duty, teaching restraint AND the fall/collapse distinction on the exact wording that
    # confuses it. It said "collapsed" here until 2026-08-19, which taught the model backwards.
    ("she tripped and fell, and her arm is bleeding heavily", '["fall","heavy_bleeding"]'),
    # CONTRASTING PAIR with the line above. Same shape - a fall plus an injury - but down
    # STAIRS, so the answer is fall_down, not fall. Without this, the model pattern-matched
    # the "tripped and fell + injury" example above and answered `fall` for a stairs fall
    # (measured 2026-08-19); Stage B then correctly rejected it as not-level-ground and the
    # fall disappeared from the briefing entirely. The examples must teach the DISTINCTION,
    # not just the shape.
    ("my father fell down the stairs and hit his head", '["fall_down","head_injury"]'),
    ("he suddenly went limp and dropped to the floor", '["collapsed"]'),
]


def _build_messages(transcript, menu):
    lines = "\n".join(f"- {sid}: {gloss}" for sid, gloss in menu)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex_stmt, ex_ans in _FEWSHOT:
        messages.append({"role": "user", "content": f"Caller's statement:\n\"{ex_stmt}\"\n\nApplicable ids:"})
        messages.append({"role": "assistant", "content": ex_ans})
    messages.append({"role": "user", "content": f"Situations:\n{lines}\n\nCaller's statement:\n\"{transcript}\"\n\nApplicable ids:"})
    return messages


def _alias_map(ontology):
    """Map the words the model might invent back onto real ids.

    Stage A paraphrases ids: it wrote "shaking" for `seizure` and "bleeding" for
    `heavy_bleeding`. String similarity misses those ("bleeding" vs "heavy_bleeding"
    scores ~0.73), so a correct answer was discarded. We therefore also index each
    entry's own trigger phrases and description words. Can only ever resolve to a REAL
    entry, so this recovers dropped answers without enabling new inventions.

    Evidence is TIERED, strongest first, because a word from the id itself outranks one
    buried in another entry's phrase - without tiers, "bleeding" (from `heavy_bleeding`)
    was cancelled by "head is bleeding" under `head_injury`. Within a tier, a term claimed
    by two entries is ambiguous and dropped rather than guessed.
    """
    tiers = [{}, {}, {}]  # 0: id itself | 1: id words + full phrases | 2: single phrase words
    for section in ("consciousness_states", "symptoms", "events"):
        for e in ontology[section]:
            eid = e["id"]
            groups = [
                {eid, eid.replace("_", " ")},
                {w for w in eid.split("_") if len(w) > 3}
                | {p.lower() for p in e.get("trigger_phrases_en", [])},
                {w for p in e.get("trigger_phrases_en", [])
                 for w in re.findall(r"[a-z]{5,}", p.lower())},
            ]
            for tier, terms in zip(tiers, groups):
                for t in terms:
                    tier[t] = None if tier.get(t, eid) != eid else eid
    return [{k: v for k, v in tier.items() if v} for tier in tiers]


def _resolve(item, valid_ids, tiers):
    """Map one model-written string onto a real id, strongest evidence first."""
    if item in valid_ids:
        return item
    key = item.lower().replace("_", " ").strip()
    for tier in tiers:
        if key in tier:
            return tier[key]
        if item.lower() in tier:
            return tier[item.lower()]
    close = difflib.get_close_matches(item, valid_ids, n=1, cutoff=0.85)
    if close:
        return close[0]
    for tier in tiers:
        close = difflib.get_close_matches(key, list(tier), n=1, cutoff=0.9)
        if close:
            return tier[close[0]]
    return None


def _parse_ids(text, valid_ids):
    """Pull a JSON array out of the model's reply and map each item to a known id.
    Fuzzy-matches near-misses (the model wrote "chocking" for "choking") with a tight
    cutoff so it can't map onto a genuinely different situation."""
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return []
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    global _ALIAS_TIERS
    if _ALIAS_TIERS is None:
        _ALIAS_TIERS = _alias_map(load_ontology())
    aliases = _ALIAS_TIERS
    result = []
    for item in raw:
        if not isinstance(item, str):
            continue
        resolved = _resolve(item, valid_ids, aliases)
        if resolved:
            result.append(resolved)
    return list(dict.fromkeys(result))  # de-dupe, keep order


# Clean one-line descriptions for the verification pass (English, internal - not shown
# to the caller, so no Japanese-verification needed). A phrase-list confused the verifier.
DESCRIPTIONS = {
    "chest_pain": "pain, tightness, or pressure in the chest",
    "difficulty_breathing": "difficulty breathing, shortness of breath, gasping, or wheezing",
    # THREE-WAY split. English "fell"/"collapsed" cover all of these, so the descriptions must
    # carry the distinction the words themselves don't: no mechanism given, level-ground trip,
    # or fall FROM HEIGHT (higher risk of spinal/multiple injury - the crew needs to know which).
    "collapsed": "the person went down with NO stated cause or mechanism - sudden, unexplained, "
                 "or described as fainting/going limp. Use this ONLY when the statement does "
                 "not say HOW they ended up on the ground",
    "fall": "the person tripped, slipped, or lost their balance on LEVEL GROUND - flat floor, "
            "pavement, a rug. NOT down stairs or a slope",
    "fall_down": "the person fell DOWN STAIRS, STEPS, OR A SLOPE - they went down something, "
                 "not over on the spot",
    "choking": "choking, or something stuck in the throat",
    "seizure": "a seizure, convulsions, or uncontrollable shaking of the body",
    "head_injury": "a blow or injury to the head",
    "heavy_bleeding": "heavy or severe bleeding",
    "severe_abdominal_pain": "severe stomach or abdominal (belly) pain",
    "high_fever": "a high fever or very high body temperature",
    "face_drooping": "one side of the face drooping, crooked, or twisted",
    "slurred_speech": "slurred, unclear, or hard-to-understand speech",
    "one_sided_weakness": "weakness or inability to move one side of the body, or one arm or leg",
    "confused": "confusion, disorientation, or not making sense when responding",
}


def _review_list(pipe, transcript, candidate_ids):
    """Single-call review over the whole proposed list (sees full context; one call, not N).

    Answers are NUMBERS, not ids. Asking for ids let the model paraphrase them into
    inventions - it replied ["shaking_uncontrollably"] instead of ["seizure"], which our
    parser then discarded, deleting a correct answer. A number cannot be paraphrased: the
    model only points at a position, and the identity comes from our own list.
    """
    if not candidate_ids:
        return []
    lines = "\n".join(
        f"{i}. {sid}: {DESCRIPTIONS.get(sid, sid)}" for i, sid in enumerate(candidate_ids, 1)
    )
    # Ask which to KEEP. The inverted form ("which are NOT mentioned?") was tried on
    # 2026-08-03 and measurably FAILED: it primes the model to hunt for things to remove,
    # so it deleted MORE. F1 fell 0.91->0.77 (set2) and 0.88->0.76 (set3), with recall
    # dropping 0.81->0.67 - the opposite of the intent. Do not re-invert without measuring.
    messages = [
        {"role": "system", "content": (
            "You review a numbered list of symptoms proposed for a caller's statement. "
            "Keep the ones the statement describes; remove ones it does not describe. "
            "Judge by meaning - callers use everyday and figurative wording. "
            "Respond with ONLY a JSON array of the NUMBERS to keep, e.g. [1,3]. "
            "Do not write symptom names. If none apply, return []."
        )},
        {"role": "user", "content": (
            f'Statement: "{transcript}"\n\nProposed symptoms:\n{lines}\n\nNumbers to keep:'
        )},
    ]
    out = pipe(messages, max_new_tokens=32, do_sample=False)
    reply = out[0]["generated_text"][-1]["content"]

    match = re.search(r"\[.*?\]", reply, re.DOTALL)
    if not match:
        return list(candidate_ids)  # unparseable -> keep everything (fail open, never delete)
    try:
        nums = json.loads(match.group(0))
    except json.JSONDecodeError:
        return list(candidate_ids)  # fail open
    keep_idx = {n for n in nums if isinstance(n, int) and 1 <= n <= len(candidate_ids)}
    return [sid for i, sid in enumerate(candidate_ids, 1) if i in keep_idx]


def classify(transcript, ontology=None, verify=True):
    ontology = ontology or load_ontology()
    menu = _situation_menu(ontology)
    valid_ids = {sid for sid, _ in menu}

    pipe = _load_pipe()
    out = pipe(_build_messages(transcript, menu), max_new_tokens=64, do_sample=False)
    candidates = _parse_ids(out[0]["generated_text"][-1]["content"], valid_ids)

    if verify:
        # Whole-list review pass: one call over the full candidate list to drop fabrications.
        candidates = _review_list(pipe, transcript, candidates)
    # Discard the critical binary statuses - the model may SELECT them (so the concept has a
    # home and doesn't displace onto no_pulse), but the deterministic step owns the answer.
    return [sid for sid in candidates if sid not in SLM_DISCARD]


if __name__ == "__main__":
    ont = load_ontology()
    # Deliberately include phrasings the crude substring matcher would MISS.
    samples = [
        "my husband clutched his chest and dropped to the floor, he's still awake",
        "she can't catch her breath and she's turning pale",
        "he took a hard fall and cracked his head on the counter",
        "grandma isn't responding at all and there's blood everywhere",
        "the baby is burning up and won't stop shaking",
    ]
    for s in samples:
        ids = classify(s, ont)
        print(f"\n{s!r}\n  -> {ids}")
