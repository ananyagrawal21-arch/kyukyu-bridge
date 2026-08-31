import re
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
# wrong place. The address is stated whenever we have one - never a silently-wrong location.
TEMPLATE_HEAD = "救急です。"
TEMPLATE_LOCATION_KNOWN = "場所は{address}です。"
# NO "not at this address" LINE EXISTS ANY MORE (removed 2026-08-20).
# Three attempts all failed for the same underlying reason:
#   「登録した住所と違います」 - leaked our internal concept of a registered address
#   「今、自宅にいません。」    - hard-coded HOME, false in a dormitory or care facility
#   「今、別の場所にいます。」  - "different from WHAT?"; the dispatcher does not know a
#                             registered address exists, so it carries no information
# The real problem was upstream: the app only works when you are AT the device, and the device
# is at the registered address, so the branch contradicted the product's own premise.
# Now: no address confirmed -> say NOTHING about location. Same omit-rather-than-guess rule as
# patient identity and unknown sex. The dispatcher asks, and carrier-level 緊急通報位置通知
# has already given them the caller's position anyway.

TEMPLATE_PATIENT = "{age}歳の{sex}です。"
TEMPLATE_PATIENT_NAMED = "名前は{name}、{age}歳の{sex}です。"
# Sex unknown -> say the age alone. 「25歳です」, never 「25歳の不明です」.
TEMPLATE_PATIENT_NO_SEX = "{age}歳です。"
TEMPLATE_PATIENT_NAMED_NO_SEX = "名前は{name}、{age}歳です。"
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

# Delivered EARLY (second, right after the address), not last. The caller will go quiet for
# up to a minute while working the app, and a dispatcher hearing silence assumes a broken line.
# Said up front, every later pause reads as "they're using the app" instead of "is anyone there?".
#
# WORDED BY THE FOUNDER (fluent, resident in Japan) 2026-08-14. Note it leads with わからない
# (cannot UNDERSTAND), not 話せません (cannot speak) - the earlier draft said only that replies
# were slow, which implies the caller follows the questions and is merely taking time. A
# dispatcher who believes that keeps asking and keeps waiting for answers that will never come.
TEMPLATE_TAIL = "すみません。日本語がわからないので、アプリを使って話しています。少々お待ちください。"


# ---- ON-SITE HANDOFF ----
# Shown to the ambulance crew when they ARRIVE, held up on the screen. Not spoken - read.
#
# POSITIONING (from OPEN_DECISIONS): do NOT compete with 救急ボイストラ on translation. That is
# deployed to 96% of fire departments already. Our unique value on scene is the PREPARED,
# VERIFIED PROFILE - age, conditions, and what was actually confirmed during the call, in
# correct Japanese. VoiceTra structurally cannot have that; it can only translate what a
# panicking family member says in the moment.
#
# TODO(founder): verify these four labels read naturally to a crew.
# NOT the same as TEMPLATE_TAIL. That one explains why answers are slow ON THE PHONE; the crew
# is standing in the room, so "replies take time" is meaningless to them. They only need the
# one fact that changes how they talk to this person.
HANDOFF_CALLER = "日本語が話せません。"

# JAPANESE ONLY, no English gloss. This screen has exactly ONE audience - the arriving crew -
# and they read Japanese. The caller is not reading it, they are holding it up, and they already
# know what it says because they answered every question that built it. A per-row English label
# served nobody and forced a crew member to scan past a foreign word on every line.
HANDOFF_LABELS = {
    "patient": "患者",
    "conditions": "持病",
    "symptoms": "症状",
    "caller": "通報者",
}


# ENGLISH LABELS FOR DEMO MODE ONLY. The real screen stays Japanese-only - see HANDOFF_LABELS.
# These exist because a competition judge with no Japanese cannot otherwise see what the crew
# is being handed, which makes the strongest on-scene feature invisible in a presentation.
HANDOFF_LABELS_EN = {
    "patient": "Patient",
    "conditions": "Conditions",
    "symptoms": "Symptoms",
    "caller": "Caller",
}


def render_handoff(
    *,
    statements: list[dict],
    age: int = None,
    sex_ja: str = None,
    name: str = None,
    conditions_ja: list[str] = None,
) -> list[dict]:
    """Rows for the crew-facing summary. Same rule as everywhere else: nothing unconfirmed.

    Each row carries BOTH forms:
      "jp"    - the row joined into one string. Kept for the CLI and any existing caller.
      "lines" - the row as SEPARATE ITEMS, which is what the screen should render.

    WHY "lines" EXISTS: symptoms used to be joined with 。 into a single cell, so the one row an
    arriving crew most needs to scan was the one row that rendered as a run-on paragraph. A crew
    member reading a held-up phone in a hallway has about three seconds; a stacked list is read
    at a glance, a paragraph is not. Founder, 2026-08-22: "it is obviously harder for them to
    understand quickly, a paragraph than a clearly organized visual layout."

    Each line also carries:
      "en"       - English gloss, for the DEMO subtitle mode only. Never shown to a real crew.
      "critical" - a cardiac-arrest-class finding, so the screen can give it visual weight.
                   息をしていません must not look identical to 頭が痛い.
    """
    def line(jp, en="", critical=False):
        return {"jp": jp, "en": en, "critical": critical}

    rows = []
    if age is not None:
        who = f"{age}歳の{sex_ja}" if sex_ja else f"{age}歳"
        en = f"{age} y/o {'male' if sex_ja == '男性' else 'female' if sex_ja == '女性' else ''}".strip()
        if name:
            who = f"{name}（{who}）"
            en = f"{name}, {en}"
        rows.append({"key": "patient", "jp": who, "lines": [line(who, en)]})

    if conditions_ja is not None:
        if conditions_ja:
            lines = [line(c) for c in conditions_ja]
            jp = "、".join(conditions_ja)
        else:
            lines, jp = [line("なし", "none")], "なし"
        rows.append({"key": "conditions", "jp": jp, "lines": lines})

    if statements:
        lines = [
            line(
                _format_statement(s["term"], s["frame"]),
                (s.get("id") or "").replace("_", " "),
                s.get("id") in CPA_IDS,
            )
            for s in statements
        ]
        # Cardiac-arrest findings first WITHIN the row. The row ORDER stays as the founder
        # settled it (患者 → 持病 → 症状 → 通報者); this only sorts inside the symptom list.
        lines.sort(key=lambda l: not l["critical"])
        rows.append({
            "key": "symptoms",
            "jp": "。".join(l["jp"] for l in lines) + "。",
            "lines": lines,
        })

    rows.append({
        "key": "caller",
        "jp": HANDOFF_CALLER,
        "lines": [line(HANDOFF_CALLER, "does not speak Japanese")],
    })
    return rows


def spoken_address(address: dict) -> str:
    """An address written the way it is SPOKEN, with 読点 between the administrative levels.

    THIS IS A PROSODY FIX, not decoration. Built as one string -
        場所は東京都江東区西葛西六丁目24の5です
    - it is a single unbroken 20-character noun phrase with NO boundary cues, so the speech
    engine has to guess where 東京都 / 江東区 / 西葛西 / 四丁目 divide and where each accent
    falls. It guesses inconsistently, and the result is heard as the pitch and emphasis
    landing at random inside the sentence. Founder reported exactly this, 2026-08-22.
    Switching to a better voice does NOT fix it, because the ambiguity is in the text.

    Each 、 gives the engine a phrase boundary: correct accent reset per component, plus the
    short pause a dispatcher writing the address down needs anyway.

    Uses the separately-stored `area` and `block_number` when present (profiles written since
    the 2026-08-22 address split), so the 丁目 and the lot number are their own phrases too.
    """
    # PREFER THE PUBLISHED READING. `kana` is Japan Post's official reading for this postal
    # code, captured at setup. Speaking it instead of the kanji removes the reading question
    # entirely - katakana has one pronunciation, so no engine can get it wrong.
    #
    # This is not a refinement, it is a correctness fix. Japanese proper nouns carry irregular
    # readings that no G2P can infer: Open JTalk renders 第三砂町 as ダイミサゴマチ rather than
    # ダイサンスナマチ, and Kyoko mangles it differently again. A misread address sends the
    # ambulance somewhere else, which is the worst failure this app has.
    kana = address.get("kana", "")
    if kana:
        parts = [kana]
        # The 丁目 suffix stays as written: numbers + 丁目 are REGULAR, and both engines read
        # them correctly (verified 四丁目 -> ヨンチョーメ). Only the proper noun needed replacing.
        area = address.get("area") or address.get("street_block", "")
        chome = re.search(r"[0-9０-９一二三四五六七八九十]+丁目$", area)
        if chome:
            parts.append(chome.group(0))
        parts.append(address.get("block_number", ""))
    else:
        parts = [address.get("prefecture", ""), address.get("city_ward", "")]
        if address.get("area") or address.get("block_number"):
            parts += [address.get("area", ""), address.get("block_number", "")]
        else:
            parts.append(address.get("street_block", ""))
    return "、".join(p for p in parts if p)


def spoken_full_address(address: dict) -> str:
    """Every address component that is safe to say in one combined sentence.

    A building's written name is not necessarily its pronunciation. Keep it out unless setup
    stored an explicit reading; never manufacture the dangling ``、号室`` when no room exists.
    This is shared by the UI and CLI so the two paths cannot disagree about safe speech.
    """
    from speak import room_to_kana

    parts = [spoken_address(address)]
    if address.get("building_kana"):
        parts.append(address["building_kana"])
    if address.get("room"):
        # room_to_kana, same as render_location_pieces. Without it this path said ヨンヒャクゴ
        # ("four hundred and five") while the split-piece path said ヨンマルゴ - the same room
        # pronounced two different ways depending on which button the caller pressed.
        parts.append(f"{room_to_kana(address['room'])}号室")
    return "、".join(p for p in parts if p)


def render_location_pieces(address: dict = None) -> list[dict]:
    """The opening line split the way a person actually gives an address on the phone.

    Measured 2026-08-12: as one sentence this is EIGHT SECONDS of continuous synthesised
    speech - prefecture, ward, block, building and room with no pauses. No dispatcher can
    write that down in one pass, and asking for a repeat is the one thing our caller cannot
    understand. Split, each piece is independently replayable, so a repeat request only
    costs the piece it applies to.

    address=None means the caller is NOT at the registered address.
    """
    if address is None:
        return [{"label": "Ambulance", "jp": TEMPLATE_HEAD}]
    area = spoken_address(address)
    # 、 before the room number too - "〇〇マンション405号室" is the same run-on problem in
    # miniature, and the room is the one part a dispatcher most needs to catch.
    #
    # BOTH PARTS ARE OPTIONAL. An empty room used to still emit 号室, producing 「…、号室です」-
    # "the room number is." with no number, which is broken Japanese and tells the dispatcher
    # nothing. Same omit-rather-than-guess rule as everywhere else: say the part we have.
    pieces = [
        {"label": "Ambulance", "jp": TEMPLATE_HEAD},
        {"label": "Area", "jp": f"場所は{area}です。"},
        # SAID HERE, ON THE DISPATCH SCREEN - not later in the briefing.
        # This line exists to explain the silence that is ABOUT TO HAPPEN: the caller now goes
        # quiet for a minute recording, confirming the transcript, checking symptoms and
        # answering the vital-sign questions. Delivered afterwards it explains a pause the
        # dispatcher has already spent a minute worrying about, which is too late to be any
        # use. Founder, 2026-08-23: "shouldn't it be right after the address and before the
        # whole transcript starts?" - yes, and that is the entire point of the line.
        {"label": "Why replies are slow", "jp": TEMPLATE_TAIL},
    ]
    # THE BUILDING NAME IS NO LONGER SPOKEN UNLESS WE HAVE ITS READING.
    # Founder, 2026-08-22: the app rendered 江東区立第三砂町小学校 as garbage. Building and
    # facility names are exactly where irregular readings live, and NO lookup gives us their
    # reading - Japan Post publishes readings for postal codes, not for buildings.
    # So this follows the project's own standing rule: OMIT RATHER THAN GUESS. The building
    # still appears on screen and on the crew handoff, where a Japanese reader reads the kanji
    # perfectly well; it is only kept out of the caller's mouth. Address + room already locates
    # someone without it, which is why the field was optional in the first place.
    # `building_kana` is honoured when a reading was captured at setup.
    from speak import room_to_kana
    spoken_building = address.get("building_kana") or ""
    room = f"{room_to_kana(address['room'])}号室" if address.get("room") else ""
    spoken = "、".join([p for p in (spoken_building, room) if p])
    if spoken:
        pieces.append({"label": "Building & room", "jp": spoken + "です。"})
    return pieces


def _format_statement(term: str, frame: str) -> str:
    if frame == "reported":
        return f"{term}と言っています"
    # observed and source_dependent are stated as-is for now.
    return term


# CARDIAC-ARREST CLASS. The official protocol (緊急度判定プロトコル Ver.1) runs
# 119通報 → 年齢・性別・住所・通報概要 → **CPA疑い判定** → 呼吸・循環・意識 → 症候別:
# arrest detection is its SECOND step, because it triggers 口頭指導 (telephone-guided CPR) and
# changes the dispatch itself.
#
# Ours used to arrive FOURTH. The vital-sign answers land in the statements list, which renders
# into the "What is happening" chunk - so a dispatcher heard an apology and the patient's age
# before learning nobody was breathing. The bug was invisible in the chunk list: the ordering
# error was in WHICH CHUNK the finding fell into, not in the order of the chunks.
#
# These are the protocol's own CPA keywords that we cover (呼吸なし・脈なし・喉が詰まった).
CPA_IDS = frozenset({"not_breathing", "no_pulse", "choking"})


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

    # 救急です always; the address only when we actually have one.
    location = TEMPLATE_LOCATION_KNOWN.format(address=address) if address is not None else ""
    chunks.append({"label": "Emergency & location", "jp": TEMPLATE_HEAD + location})

    # CPA FINDINGS JUMP THE QUEUE - ahead of even the "replies are slow" line. If the patient
    # is not breathing, that beats an apology: it is what starts telephone-guided CPR.
    # They are REMOVED from `statements` here so the later symptom chunk cannot repeat them.
    cpa = [s for s in statements if s.get("id") in CPA_IDS]
    if cpa:
        statements = [s for s in statements if s.get("id") not in CPA_IDS]
        chunks.append({
            "label": "CRITICAL",
            "jp": "。".join(_format_statement(s["term"], s["frame"]) for s in cpa) + "。",
        })

    # Kept in the chunk list as a REPLAY, not as its first delivery - render_location_pieces
    # now says it on the dispatch screen, before the caller goes quiet. A dispatcher who asks
    # "are you still there?" mid-call can still press it again here.
    chunks.append({"label": "Why replies are slow (replay)", "jp": TEMPLATE_TAIL})

    if age is not None:
        if sex_ja:
            jp = (
                TEMPLATE_PATIENT_NAMED.format(name=name, age=age, sex=sex_ja) if name
                else TEMPLATE_PATIENT.format(age=age, sex=sex_ja)
            )
        else:
            jp = (
                TEMPLATE_PATIENT_NAMED_NO_SEX.format(name=name, age=age) if name
                else TEMPLATE_PATIENT_NO_SEX.format(age=age)
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

    return chunks


def render_briefing(**kwargs) -> str:
    """The whole briefing as one string (chunks joined) - kept for CLI/tests."""
    return "".join(c["jp"] for c in render_briefing_chunks(**kwargs))
