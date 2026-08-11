# The briefing is SPOKEN ALOUD by the caller, in the first person. So it is written as
# natural speech with subjects dropped (Japanese does this freely), not as a terse
# third-person report. "通報者は日本語が不自由です" became "日本語が話せません".
#
# Each matched symptom is phrased according to its FRAME (see ontology.json):
#   reported  -> "<term>と言っています"  (the patient said it: implies conscious, talking)
#   observed  -> "<term>"               (the caller saw it directly)
#   source_dependent -> stated plainly for now; the Week-2 SLM will choose the frame.
#
# Patient details (age/sex/conditions) are omitted unless the caller confirmed the
# emergency is about the person in profile.json - a wrong age is worse than none.
#
# REGISTER RULE (settled 2026-08-12). The two frames need DIFFERENT forms, because one is
# quoted and the other is not:
#   observed -> polite (です/ます). Stated as a standalone sentence to the dispatcher:
#               「冷や汗をかいています。」「倒れました。」
#   reported -> PLAIN form, because it gets wrapped in と言っています, and quoted speech
#               takes plain form: 「頭が痛いと言っています」, never 「頭が痛いですと言っています」.
# Four terms taken from the protocol's dispatcher-side question phrasing (「吐き気がありますか？」)
# were stored polite and produced 「吐き気がありますと言っています」; fixed to plain form.
# When adding a reported-frame term, store the PLAIN form.

# Location is the single most critical field: a wrong address sends the ambulance to the
# wrong place. So we only state the home address when the caller confirms they are there.
# Otherwise we say plainly they are not home - never a silently-wrong location - prompting
# the dispatcher to ask where they actually are.
TEMPLATE_HEAD = "救急です。"
TEMPLATE_LOCATION_KNOWN = "場所は{address}です。"
# Rewritten 2026-08-04 (was 「登録した住所と違います」 - leaked our internal app concept,
# meaningless to a dispatcher). Now a plain, natural statement that simply signals no address
# is coming, so the dispatcher knows to ask. TODO(founder): confirm this reads naturally.
TEMPLATE_LOCATION_UNKNOWN = "今、自宅にいません。"

TEMPLATE_PATIENT = "{age}歳の{sex}です。"
TEMPLATE_PATIENT_NAMED = "名前は{name}、{age}歳の{sex}です。"
TEMPLATE_CONDITIONS = "持病は{conditions}です。"
NO_CONDITIONS = "持病はありません。"
# The dispatcher's near-certain first question is the caller's own name (通報者の名前),
# for callback purposes - independent of which patient the emergency is about.
TEMPLATE_CALLER_NAME = "私の名前は{name}です。"

# When nothing matched, we omit the symptom line entirely rather than announce "unknown" -
# the dispatcher will ask, and airtime is precious. (Founder decision.)

# Natural spoken lead-in for the caller's own words when the ontology could not cover them.
# Populated only once the SLM can translate free speech (dormant until then). The
# verified/unverified visual separation is a UI concern, handled on screen, not in speech.
TEMPLATE_CALLER_WORDS = "あと、{caller_description}。"

TEMPLATE_TAIL = "日本語が話せません。"


def _format_statement(term: str, frame: str) -> str:
    if frame == "reported":
        return f"{term}と言っています"
    # observed and source_dependent are stated as-is for now.
    return term


def render_briefing_chunks(
    *,
    address: str = None,
    statements: list[dict],
    age: int = None,
    sex_ja: str = None,
    name: str = None,
    conditions_ja: list[str] = None,
    caller_description: str = "",
    caller_name: str = None,
) -> list[dict]:
    """The briefing as ORDERED, LABELLED chunks - so the caller can deliver it one piece
    at a time, at the dispatcher's note-taking pace, instead of one long blast.
    Each chunk: {"label": <English, for the UI>, "jp": <Japanese to read aloud>}.
    Order leads with the most urgent (emergency + location -> gets the ambulance moving).
    TODO(founder): the chunk ORDER is a dispatch-flow decision, tune as needed."""
    chunks = []

    location = (
        TEMPLATE_LOCATION_KNOWN.format(address=address) if address is not None
        else TEMPLATE_LOCATION_UNKNOWN
    )
    chunks.append({"label": "Emergency & location", "jp": TEMPLATE_HEAD + location})

    if age is not None and sex_ja is not None:
        jp = (
            TEMPLATE_PATIENT_NAMED.format(name=name, age=age, sex=sex_ja) if name
            else TEMPLATE_PATIENT.format(age=age, sex=sex_ja)
        )
        chunks.append({"label": "Patient", "jp": jp})

    if statements:
        sentences = [_format_statement(s["term"], s["frame"]) for s in statements]
        chunks.append({"label": "What is happening", "jp": "。".join(sentences) + "。"})

    if conditions_ja is not None:
        cond = (
            TEMPLATE_CONDITIONS.format(conditions="、".join(conditions_ja))
            if conditions_ja else NO_CONDITIONS
        )
        chunks.append({"label": "Known conditions", "jp": cond})

    if caller_description:
        chunks.append({
            "label": "In the caller's own words",
            "jp": TEMPLATE_CALLER_WORDS.format(caller_description=caller_description),
        })

    if caller_name:
        chunks.append({"label": "Your name", "jp": TEMPLATE_CALLER_NAME.format(name=caller_name)})

    chunks.append({"label": "Caller can't speak Japanese", "jp": TEMPLATE_TAIL})
    return chunks


def render_briefing(**kwargs) -> str:
    """The whole briefing as one string (chunks joined) - kept for CLI/tests."""
    return "".join(c["jp"] for c in render_briefing_chunks(**kwargs))
