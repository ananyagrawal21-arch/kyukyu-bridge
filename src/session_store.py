"""The link between the caller's phone and the dispatcher's console.

Every message that crosses between the two ends passes through here, gets the envelope defined in
PROTOCOL.md section 1, and is written to a per-session log. The phone page and the console page
run in the same Streamlit process for the demo, so one shared SessionStore instance IS the relay.
Splitting it into a separate server later changes the transport, not this file's rules.
"""
import hashlib
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = "1"
JST = timezone(timedelta(hours=9))

# PROTOCOL.md sections 3 and 4. A type not listed for its direction is malformed - the console
# must never receive something it has no rule for.
TYPES = {
    "phone_to_console": {
        "session.start", "session.end", "profile", "situation",
        "transcript", "answer", "event", "ack",
    },
    "console_to_phone": {"question", "free_text", "command", "ack", "session.end"},
}

# PROTOCOL.md section 6: the profile is the only message that carries the real address. In the
# log it is replaced by a hash - enough to prove two runs used the same profile, not enough to
# be an address.
_REDACT_IN_LOG = {"profile"}


def mint_session_id(now: datetime = None) -> str:
    """PROTOCOL.md section 7: kb-<YYYYMMDD>-<6 hex>. Nothing derived from the person."""
    now = now or datetime.now(JST)
    return f"kb-{now:%Y%m%d}-{secrets.token_hex(3)}"


def _now() -> datetime:
    return datetime.now(JST)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def _profile_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


class SessionStore:
    def __init__(self, log_dir):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Streamlit serves every browser tab on its own thread, and the phone and the console are
        # two tabs writing to the same session. Without the lock, two messages can take the same
        # seq number - and a duplicated seq hides a lost message, the failure seq exists to catch.
        self._lock = threading.Lock()
        self._sessions = {}

    # ---- opening and closing ----

    def start(self, session_id: str, config: dict = None, drill: bool = False,
              ts_device: str = None) -> dict:
        """Open a session. The server's clock at this moment is t0 for every measurement."""
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"session {session_id} already exists")
            t0 = _now()
            self._sessions[session_id] = {
                "t0": t0,
                "drill": bool(drill),
                "ended": False,
                "messages": [],
                "seq": {d: 0 for d in TYPES},
                "next_msg": 1,
            }
        payload = dict(config or {})
        payload["t0"] = _iso(t0)
        return self.send(session_id, "phone_to_console", "session.start", payload, ts_device)

    def end(self, session_id: str, reason: str, direction: str = "phone_to_console") -> dict:
        return self.send(session_id, direction, "session.end", {"reason": reason})

    # ---- the one way anything crosses ----

    def send(self, session_id: str, direction: str, type_: str, payload: dict,
             ts_device: str = None) -> dict:
        """Wrap a payload in the envelope, store it, log it, and return the envelope.

        Raises ValueError for anything malformed, after writing a `malformed` line to the log.
        Raising rather than quietly dropping: in a demo, a silently lost message looks exactly
        like a working system that the dispatcher is ignoring.
        """
        with self._lock:
            problem = self._check(session_id, direction, type_, payload)
            if problem:
                self._log_malformed(session_id, direction, type_, problem)
                raise ValueError(problem)

            s = self._sessions[session_id]
            ts_server = _now()
            s["seq"][direction] += 1
            envelope = {
                "schema_version": SCHEMA_VERSION,
                "session_id": session_id,
                "msg_id": f"m-{s['next_msg']:03d}",
                "seq": s["seq"][direction],
                "direction": direction,
                "type": type_,
                "ts_device": ts_device,
                "ts_server": _iso(ts_server),
                "t_rel_ms": int((ts_server - s["t0"]).total_seconds() * 1000),
                "drill": s["drill"],
                "payload": payload,
            }
            s["next_msg"] += 1
            s["messages"].append(envelope)
            if type_ == "session.end":
                s["ended"] = True
            self._write(session_id, envelope)
            return envelope

    def _check(self, session_id, direction, type_, payload):
        if session_id not in self._sessions:
            return f"unknown session {session_id}"
        if direction not in TYPES:
            return f"unknown direction {direction}"
        if type_ not in TYPES[direction]:
            return f"type {type_} not allowed {direction}"
        if not isinstance(payload, dict):
            return "payload must be a dict"
        if self._sessions[session_id]["ended"]:
            return f"session {session_id} has ended"
        return None

    # ---- reading ----

    def messages(self, session_id: str, direction: str = None, after_seq: int = 0) -> list:
        """Messages in arrival order. `after_seq` lets a polling page fetch only what is new.

        seq counts per direction, so `after_seq` only applies when a direction is given.
        """
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                return []
            if direction is None:
                return list(s["messages"])
            return [m for m in s["messages"]
                    if m["direction"] == direction and m["seq"] > after_seq]

    def latest(self, session_id: str, type_: str):
        """The most recent message of one type - e.g. the current `situation` revision."""
        for m in reversed(self.messages(session_id)):
            if m["type"] == type_:
                return m
        return None

    def sessions(self) -> list:
        """Newest first. What the console lists."""
        with self._lock:
            rows = [
                {"session_id": sid, "t0": _iso(s["t0"]), "drill": s["drill"],
                 "ended": s["ended"], "n_messages": len(s["messages"])}
                for sid, s in self._sessions.items()
            ]
        return sorted(rows, key=lambda r: r["t0"], reverse=True)

    # ---- the log ----

    def _write(self, session_id, envelope):
        line = envelope
        if envelope["type"] in _REDACT_IN_LOG:
            line = dict(envelope, payload={"profile_hash": _profile_hash(envelope["payload"])})
        with open(self.log_dir / f"{session_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _log_malformed(self, session_id, direction, type_, problem):
        # Payload deliberately not logged: a malformed message could still contain the address.
        name = session_id if session_id in self._sessions else "_malformed"
        entry = {"type": "malformed", "session_id": session_id, "direction": direction,
                 "attempted_type": type_, "problem": problem, "ts_server": _iso(_now())}
        with open(self.log_dir / f"{name}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
