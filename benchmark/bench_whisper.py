"""
Whisper latency benchmark: PyTorch vs OpenVINO, on the SAME machine.

Isolates OpenVINO's contribution (unlike comparing two different laptops).
Runs correctness check too - the OpenVINO transcript must match PyTorch's,
otherwise a speedup is meaningless.

Develop/test on any machine for correctness; run on an Intel CPU for the real
numbers to present. Speed on non-Intel hardware is NOT representative.

Usage:
    python bench_whisper.py --audio ../data/bench_clip.wav --model openai/whisper-small
"""
import argparse
import re
import statistics
import time
from pathlib import Path

import soundfile as sf


def normalize(text):
    """Compare on words only - OpenVINO may drop punctuation/casing, which is
    cosmetic and does not affect our word-based ontology matching."""
    return re.sub(r"[^\w\s]", "", text.lower()).split()


def load_audio(path):
    """Return 16 kHz mono float32, matching how the real pipeline feeds Whisper."""
    import torch
    import torchaudio

    audio, sr = sf.read(path)
    wav = torch.tensor(audio, dtype=torch.float32)
    if wav.ndim > 1:
        wav = wav.mean(dim=1)
    if sr != 16000:
        wav = torchaudio.functional.resample(wav, orig_freq=sr, new_freq=16000)
    return wav.numpy(), len(wav) / 16000


def time_runs(transcribe, audio, warmup=1, runs=5):
    """Run once to warm up (excluded), then time `runs` transcriptions."""
    for _ in range(warmup):
        transcribe(audio)
    times = []
    text = None
    for _ in range(runs):
        t0 = time.perf_counter()
        text = transcribe(audio)
        times.append(time.perf_counter() - t0)
    return text, times


def summarize(label, times):
    print(f"  {label:18s} median {statistics.median(times):.3f}s  "
          f"mean {statistics.mean(times):.3f}s  min {min(times):.3f}s  "
          f"(n={len(times)})")


def build_pytorch(model_id):
    from transformers import pipeline
    # Force CPU (device=-1): the real target is an Intel CPU, and it avoids Apple-GPU
    # (MPS) tensors that OpenVINO can't consume.
    asr = pipeline("automatic-speech-recognition", model=model_id, device=-1)
    return lambda a: asr({"array": a, "sampling_rate": 16000})["text"].strip()


def build_openvino(model_id, int8=False):
    from transformers import AutoProcessor, pipeline
    from optimum.intel import OVModelForSpeechSeq2Seq

    kwargs = {"export": True}
    if int8:
        from optimum.intel import OVWeightQuantizationConfig
        kwargs["quantization_config"] = OVWeightQuantizationConfig(bits=8)

    model = OVModelForSpeechSeq2Seq.from_pretrained(model_id, **kwargs)
    processor = AutoProcessor.from_pretrained(model_id)
    asr = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        device=-1,  # keep inputs on CPU for the OpenVINO runtime
    )
    return lambda a: asr({"array": a, "sampling_rate": 16000})["text"].strip()


def main():
    p = argparse.ArgumentParser()
    # Not required: with required=True the script aborts at parse_args() when launched from
    # an IDE Run/Debug button (which passes no arguments), which looks like a bug in the code.
    # Defaults to a bundled clip, resolved relative to THIS file so the working directory
    # does not matter.
    # A SYNTHESISED clip, deliberately. The earlier default was a real human recording, which
    # meant a personal voice sample lived in the repo for no reason - this measures latency, and
    # latency depends on clip length, not on who is speaking.
    default_audio = str(Path(__file__).resolve().parent.parent / "data" / "bench_clip.wav")
    p.add_argument("--audio", default=default_audio)
    # Default matches the actual product model (src/stt.py DEFAULT_MODEL) as of 2026-08-04 -
    # keep these in sync, otherwise the benchmark numbers describe a model we don't ship.
    p.add_argument("--model", default="openai/whisper-small")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--skip-int8", action="store_true", help="skip the INT8 variant")
    args = p.parse_args()

    audio, dur = load_audio(args.audio)
    print(f"\nAudio: {dur:.1f}s   Model: {args.model}   Runs: {args.runs}\n")

    # Every stage is independent and failure-isolated. A crash in one conversion must never
    # throw away results already measured - that wasted a full slow run on the Intel machine.
    def stage(label, builder):
        print(f"\n{label}:")
        try:
            text, times = time_runs(builder(), audio, runs=args.runs)
            summarize(label, times)
            return text, times
        except Exception as e:
            print(f"  FAILED -> {type(e).__name__}: {e}")
            print(f"  (skipping {label}; other results below are still valid)")
            return None, None

    pt_text, pt_times = stage("pytorch", lambda: build_pytorch(args.model))
    if pt_times is None:
        print("\nPyTorch baseline failed - cannot compute speedups. Stopping.")
        return

    ov_text, ov_times = stage("openvino-fp", lambda: build_openvino(args.model))

    ov8_text, ov8_times = None, None
    if not args.skip_int8:
        ov8_text, ov8_times = stage("openvino-int8", lambda: build_openvino(args.model, int8=True))

    print("\n--- Correctness (word content must match; punctuation ignored) ---")
    base_words = normalize(pt_text)

    def verdict(text):
        return "MATCH" if normalize(text) == base_words else "DIFFERS"

    print(f"  pytorch : {pt_text!r}")
    if ov_text is not None:
        print(f"  ov-fp   : {ov_text!r}  [{verdict(ov_text)}]")
    if ov8_text is not None:
        print(f"  ov-int8 : {ov8_text!r}  [{verdict(ov8_text)}]")

    # Short summary, kept to a few lines so it can be read off screen or photographed.
    base = statistics.median(pt_times)
    print("\n=============== SUMMARY ===============")
    print(f"  pytorch        {base:6.2f}s   1.00x")
    if ov_times:
        m = statistics.median(ov_times)
        print(f"  openvino-fp    {m:6.2f}s   {base/m:.2f}x   [{verdict(ov_text)}]")
    if ov8_times:
        m8 = statistics.median(ov8_times)
        print(f"  openvino-int8  {m8:6.2f}s   {base/m8:.2f}x   [{verdict(ov8_text)}]")
    print("=======================================")


if __name__ == "__main__":
    main()
