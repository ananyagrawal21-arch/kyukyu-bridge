"""Offline Japanese speech.

WHY THIS MATTERS: the caller does not read Japanese. The briefing on screen is text they
cannot pronounce, so the app has to SAY it for them - they play it to the dispatcher.
That makes this part of the core delivery path, not decoration.

TWO LAYERS, and the first is the important one:

1. PRE-RENDERED AUDIO (data/audio/) - the real answer. Every sentence this app can speak is
   known ahead of time: the fixed lines are constants, the 29 ontology terms are a closed set,
   and the profile-derived lines (address, age, conditions) are settled when the profile is
   written, not during a call. So we render every sentence ONCE with the best voice available
   anywhere, ship the WAVs, and at runtime just play files.

   This is only possible BECAUSE the ontology is closed - the same property the safety
   architecture rests on. It buys: identical audio on every machine, no OS voice dependency
   (Windows SAPI5 needs a Japanese language pack that may simply not be there), no synthesis
   during an emergency, and no extra model in memory.

2. LIVE SYNTHESIS - fallback only, and what the build script itself uses.
   macOS `say`, then pyttsx3 (SAPI5 on Windows), both offline.

Multi-sentence text is split on 。 and the pieces concatenated, so a briefing chunk that
combines several symptoms never needs its own pre-rendered file - only the individual
sentences do. Otherwise every possible COMBINATION of symptoms would need rendering.
"""
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

# Two directories, and the split is a PRIVACY boundary, not organisation.
#   audio/          fixed lines + the 29 ontology terms. Identical for every user, committed.
#   audio/profile/  the address, name, age, conditions - SPOKEN ALOUD. Committing these would
#                   leak a real home address as audio, exactly what gitignoring profile.json
#                   prevents for text. Gitignored, and rebuilt per install.
AUDIO_DIR = Path(__file__).resolve().parent.parent / "data" / "audio"
PROFILE_AUDIO_DIR = AUDIO_DIR / "profile"

# Preferred macOS Japanese voice, best first - the first one actually installed wins.
# "Kyoko (Enhanced)" is a downloaded higher-quality voice with real intonation; plain "Kyoko"
# is the old built-in and sounds flat and robotic, which makes a dispatcher work harder to
# follow an address read aloud. Enhanced/Premium voices are NOT present by default - they come
# from System Settings > (search "voice") > Manage Voices - so we fall back gracefully.
_MAC_JA_VOICES = ("Kyoko (Premium)", "Kyoko (Enhanced)", "Kyoko")


def _mac_voice() -> str:
    """First preferred voice that is actually installed on this machine."""
    try:
        listed = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    except (OSError, subprocess.SubprocessError):
        return _MAC_JA_VOICES[-1]
    for name in _MAC_JA_VOICES:
        if name in listed:
            return name
    return _MAC_JA_VOICES[-1]


def _mac_say(text: str):
    if platform.system() != "Darwin" or not shutil.which("say"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        subprocess.run(
            ["say", "-v", _mac_voice(), "-o", path,
             "--data-format=LEI16@22050", text],
            check=True, capture_output=True,
        )
        with open(path, "rb") as f:
            return f.read()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    finally:
        os.unlink(path) if os.path.exists(path) else None


def _pyttsx3(text: str):
    """Cross-platform: uses whatever Japanese voice the OS provides."""
    try:
        import pyttsx3
    except ImportError:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        engine = pyttsx3.init()
        for v in engine.getProperty("voices"):
            blob = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
            if "ja" in blob or "japan" in blob:
                engine.setProperty("voice", v.id)
                break
        engine.save_to_file(text, path)
        engine.runAndWait()
        with open(path, "rb") as f:
            data = f.read()
        return data or None
    except Exception:
        return None
    finally:
        os.unlink(path) if os.path.exists(path) else None


BACKENDS = (_mac_say, _pyttsx3)


def synthesize(text: str):
    """Live TTS. Used by tools/build_audio.py and as the runtime fallback."""
    if not text.strip():
        return None
    for backend in BACKENDS:
        audio = backend(text)
        if audio:
            return audio
    return None


# Japanese addresses are WRITTEN with hyphens and SPOKEN with の: 24-5 is read
# "にじゅうよん の ご", never with a hyphen sound. A speech engine given "24-5" either swallows
# the hyphen or says "minus", so a dispatcher hears the wrong address - the single most
# critical field. Only a hyphen BETWEEN DIGITS is converted, so the long-vowel ー inside words
# like マンション is untouched.
_ADDR_HYPHEN = re.compile(r"(?<=[0-9０-９])[-−‐―ー](?=[0-9０-９])")

# Full-width digits are also read less reliably than half-width, so normalise them.
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def speech_form(text: str) -> str:
    """How this text should be SPOKEN, which is not always how it is written.

    Applied to everything before synthesis AND before the cache lookup, so the recording and
    the request always agree. The on-screen text keeps the written form.
    """
    return _ADDR_HYPHEN.sub("の", text).translate(_FULLWIDTH_DIGITS)


def split_sentences(text: str) -> list:
    """Atomic units for caching. Keeps the 。 so each piece is a complete spoken sentence,
    and normalises each to its spoken form."""
    return [speech_form(s + "。") for s in re.split(r"。", text) if s.strip()]


def cache_key(sentence: str) -> str:
    """Filename for one sentence. Content-addressed, so changing a term's wording simply
    misses the cache and gets rebuilt - stale audio can never silently outlive its text."""
    return hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:16]


def cache_path(sentence: str, profile_specific: bool = False) -> Path:
    """Where this sentence's WAV lives. Profile-derived audio goes in the gitignored subfolder."""
    base = PROFILE_AUDIO_DIR if profile_specific else AUDIO_DIR
    return base / f"{cache_key(sentence)}.wav"


def _find(sentence: str):
    """Look in both directories - at playback we do not know or care which kind it was."""
    for base in (AUDIO_DIR, PROFILE_AUDIO_DIR):
        p = base / f"{cache_key(sentence)}.wav"
        if p.exists():
            return p
    return None


def _concat_wavs(paths: list):
    """Join pre-rendered sentences into one clip. All were produced by the same build run,
    so the formats match by construction."""
    out = io.BytesIO()
    writer = None
    try:
        for p in paths:
            with wave.open(str(p), "rb") as r:
                if writer is None:
                    writer = wave.open(out, "wb")
                    writer.setparams(r.getparams())
                writer.writeframes(r.readframes(r.getnframes()))
    except (wave.Error, OSError):
        return None
    finally:
        if writer is not None:
            writer.close()
    return out.getvalue() or None


def from_cache(text: str):
    """Pre-rendered audio for this text, or None if any sentence is missing."""
    pieces = split_sentences(text)
    if not pieces:
        return None
    paths = [_find(p) for p in pieces]
    if not all(paths):
        return None
    return _concat_wavs(paths)


def speak_japanese(text: str):
    """WAV bytes for Japanese text: pre-rendered if available, else synthesised live."""
    if not text.strip():
        return None
    return from_cache(text) or synthesize(text)


def available_backend() -> str:
    """Which path would be used (for diagnostics)."""
    if from_cache("救急です。"):
        return "pre-rendered audio (data/audio/)"
    for backend in BACKENDS:
        if backend("テスト"):
            return f"live synthesis: {backend.__name__}"
    return "none"


if __name__ == "__main__":
    print("backend:", available_backend())
    audio = speak_japanese("救急です。場所は東京都江東区です。息が苦しいです。")
    print("wav bytes:", len(audio) if audio else "FAILED")
