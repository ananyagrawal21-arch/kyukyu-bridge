"""Measure transcription latency: plain transformers vs the OpenVINO INT8 build.

    python benchmark/bench_stt_backends.py [clip.wav]

Produces the number the pitch needs - what Intel's toolkit actually bought on the speech
stage - and, just as importantly, checks the transcript did not change. A speedup that
quietly degrades what a panicking caller said is not a win.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import stt  # noqa: E402

CLIP = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "bench_clip.wav"
RUNS = 3


def load_clip(path):
    """Decode the WAV ourselves and hand the pipeline an array.

    NOT just convenience: passing a FILENAME makes transformers shell out to ffmpeg, which
    this machine does not have and the app never uses. The app decodes with prepare_audio and
    passes an array, so benchmarking the array path measures what actually ships.
    """
    import wave
    import numpy as np
    with wave.open(str(path), "rb") as r:
        sr = r.getframerate()
        x = np.frombuffer(r.readframes(r.getnframes()), dtype=np.int16)
        if r.getnchannels() > 1:
            x = x.reshape(-1, r.getnchannels()).mean(axis=1)
    arr = stt.prepare_audio(x.astype(np.float32) / 32768.0, sr)
    return {"raw": arr, "sampling_rate": stt.WHISPER_SAMPLE_RATE}


def timed(pipe, clip):
    """Warm once (first call pays graph-compile/allocation), then take the best of RUNS.
    Best rather than mean: we are measuring the machine, and the outliers are other processes."""
    # THE SAME KWARGS THE APP USES. An earlier version passed only {language, task}, which
    # measured a configuration the app never runs and hid a crash: ROBUST_GENERATE_KWARGS turns
    # on temperature-fallback decoding, and the OpenVINO wrapper does not implement the
    # prepare_inputs_for_generation signature that path needs. Benchmarking anything other than
    # the shipped settings is how you publish a speedup for code nobody executes.
    kw = dict(stt.ROBUST_GENERATE_KWARGS, language="en", task="transcribe")
    call = lambda: pipe(dict(clip), generate_kwargs=kw)
    call()
    best, text = float("inf"), ""
    for _ in range(RUNS):
        t0 = time.perf_counter()
        out = call()
        best = min(best, time.perf_counter() - t0)
        text = out["text"].strip()
    return best, text


def main():
    if not CLIP.exists():
        sys.exit(f"No clip at {CLIP} - pass one as an argument.")
    print(f"clip: {CLIP.name}\nruns: {RUNS} (best of)\n")
    clip = load_clip(CLIP)

    from transformers import pipeline
    base = pipeline("automatic-speech-recognition", model=stt.DEFAULT_MODEL, device=-1)
    t_base, txt_base = timed(base, clip)
    print(f"transformers (CPU fp32) : {t_base:6.2f}s")

    if not stt._ov_available():
        print("\nOpenVINO IR not found - run benchmark/convert_whisper.py first.")
        return

    stt._asr_cache.clear()
    stt._OV_ENABLED = True   # the app keeps this OFF; force it on to measure
    try:
        t_ov, txt_ov = timed(stt.get_asr(), clip)
    except Exception as exc:  # noqa: BLE001
        print(f"\nOpenVINO path FAILED with the app's real settings:\n  {type(exc).__name__}: {exc}")
        return
    print(f"OpenVINO INT8           : {t_ov:6.2f}s   ({t_base / t_ov:.2f}x)")

    print("\ntranscripts identical:", txt_base == txt_ov)
    if txt_base != txt_ov:
        print(f"  transformers: {txt_base}")
        print(f"  openvino    : {txt_ov}")


if __name__ == "__main__":
    main()
