import json
import re
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from session_store import SessionStore, mint_session_id

FAKE_ADDRESS = {"prefecture": "東京都", "city_ward": "テスト区", "area": "架空町1丁目",
                "block_number": "2-3", "building": "テストハイツ", "room": "101"}


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path)


def _log(tmp_path, sid):
    return [json.loads(l) for l in (tmp_path / f"{sid}.jsonl").read_text().splitlines()]


def test_session_id_has_no_personal_data():
    assert re.fullmatch(r"kb-\d{8}-[0-9a-f]{6}", mint_session_id())


def test_envelope_has_every_protocol_field(store):
    sid = mint_session_id()
    env = store.start(sid, {"commit_hash": "abc"})
    for field in ("schema_version", "session_id", "msg_id", "seq", "direction", "type",
                  "ts_device", "ts_server", "t_rel_ms", "drill", "payload"):
        assert field in env
    assert env["payload"]["t0"]


def test_seq_counts_per_direction_without_gaps(store):
    sid = mint_session_id()
    store.start(sid)
    a = store.send(sid, "phone_to_console", "event", {"event": "app_opened"})
    q = store.send(sid, "console_to_phone", "question", {"question_id": "q1"})
    b = store.send(sid, "phone_to_console", "event", {"event": "call_dialing"})
    assert (a["seq"], b["seq"]) == (2, 3)          # session.start was phone seq 1
    assert q["seq"] == 1
    ids = [m["msg_id"] for m in store.messages(sid)]
    assert len(ids) == len(set(ids))


def test_concurrent_senders_never_share_a_seq(store):
    sid = mint_session_id()
    store.start(sid)

    def burst():
        for _ in range(50):
            store.send(sid, "phone_to_console", "event", {"event": "x"})

    threads = [threading.Thread(target=burst) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = [m["seq"] for m in store.messages(sid, "phone_to_console")]
    assert sorted(seqs) == list(range(1, 202))     # 1 start + 200 events, no gaps, no repeats


def test_after_seq_returns_only_new_messages(store):
    sid = mint_session_id()
    store.start(sid)
    store.send(sid, "console_to_phone", "question", {"question_id": "q1"})
    store.send(sid, "console_to_phone", "question", {"question_id": "q2"})
    new = store.messages(sid, "console_to_phone", after_seq=1)
    assert [m["payload"]["question_id"] for m in new] == ["q2"]


def test_drill_flag_is_on_every_message(store):
    sid = mint_session_id()
    store.start(sid, drill=True)
    env = store.send(sid, "phone_to_console", "event", {"event": "x"})
    assert env["drill"] is True


def test_address_never_reaches_the_log(store, tmp_path):
    sid = mint_session_id()
    store.start(sid)
    store.send(sid, "phone_to_console", "profile", {"address": FAKE_ADDRESS})
    raw = (tmp_path / f"{sid}.jsonl").read_text()
    assert "架空町" not in raw and "テストハイツ" not in raw
    profile_line = [l for l in _log(tmp_path, sid) if l["type"] == "profile"][0]
    assert set(profile_line["payload"]) == {"profile_hash"}
    # ...while the console, reading from memory, still gets the real thing.
    assert store.latest(sid, "profile")["payload"]["address"] == FAKE_ADDRESS


def test_wrong_direction_type_is_rejected_and_logged(store, tmp_path):
    sid = mint_session_id()
    store.start(sid)
    with pytest.raises(ValueError):
        store.send(sid, "phone_to_console", "question", {})  # questions only go the other way
    assert _log(tmp_path, sid)[-1]["type"] == "malformed"


def test_unknown_session_is_rejected(store):
    with pytest.raises(ValueError):
        store.send("kb-20260101-000000", "phone_to_console", "event", {})


def test_nothing_crosses_after_the_session_ends(store):
    sid = mint_session_id()
    store.start(sid)
    store.end(sid, "completed")
    with pytest.raises(ValueError):
        store.send(sid, "phone_to_console", "event", {"event": "late"})
    assert store.sessions()[0]["ended"] is True


def test_latest_returns_newest_situation_revision(store):
    sid = mint_session_id()
    store.start(sid)
    store.send(sid, "phone_to_console", "situation", {"revision": 1, "items": []})
    store.send(sid, "phone_to_console", "situation", {"revision": 2, "items": []})
    assert store.latest(sid, "situation")["payload"]["revision"] == 2
