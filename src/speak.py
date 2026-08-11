"""Offline Japanese text-to-speech.

WHY THIS MATTERS: the caller does not read Japanese. The briefing on screen is text they
cannot pronounce, so the app has to SAY it for them - they play it to the dispatcher.
That makes TTS part of the core delivery path, not decoration.

Pluggable backends, tried in order. All are OFFLINE (no network):
  1. macOS `say`      - built-in Japanese voices (Kyoko etc). Dev machine.
  2. pyttsx3          - wraps the OS voice engine (SAPI5 on Windows, NSSS on macOS),
                        so the same code works on the Intel/Windows demo machine,
                        PROVIDED a Japanese voice is installed in the OS.
Returns WAV bytes so the UI can play it; None if no backend is available.
"""
import os
import platform
import shutil
import subprocess
import tempfile

# Preferred macOS Japanese voice; any ja_JP voice works.
_MAC_JA_VOICE = "Kyoko"


def _mac_say(text: str):
    if platform.system() != "Darwin" or not shutil.which("say"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        subprocess.run(
            ["say", "-v", _MAC_JA_VOICE, "-o", path,
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


def speak_japanese(text: str):
    """Render Japanese text to WAV bytes offline, or None if no backend works."""
    if not text.strip():
        return None
    for backend in BACKENDS:
        audio = backend(text)
        if audio:
            return audio
    return None


def available_backend() -> str:
    """Which backend would be used (for diagnostics)."""
    for backend in BACKENDS:
        if backend("テスト"):
            return backend.__name__
    return "none"


if __name__ == "__main__":
    print("backend:", available_backend())
    audio = speak_japanese("救急です。場所は東京都江東区です。息が苦しいです。")
    print("wav bytes:", len(audio) if audio else "FAILED")
