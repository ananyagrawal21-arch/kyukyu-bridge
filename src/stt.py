"""Speech-to-text - the single source of truth for both the CLI and the app.

Robustness settings target the two failures we actually observed:
  1. Whisper hallucinating repeated filler on quiet/disfluent audio
     (a real clip once produced "You're free to go." x70).
  2. Language auto-detection going wrong on short or accented speech, which
     corrupts the whole transcript. We know the caller's language from their
     profile, so we tell Whisper instead of letting it guess.
"""
import os
from pathlib import Path

WHISPER_SAMPLE_RATE = 16000
# whisper-small over base (2026-08-04): tested on real Vietnamese/Hindi accented speech
# (L2-ARCTIC corpus, not synthetic). Base badly garbled one Vietnamese clip; small fixed it
# to near-exact. Small halved mean WER (0.141 -> 0.081) at ~1-2s extra latency once warm.
DEFAULT_MODEL = "openai/whisper-small"

# Anti-hallucination decoding settings.
#   condition_on_prev_tokens=False  - stops the repetition death-spiral, where one bad
#                                     segment conditions the next and the model loops.
#   temperature fallback            - if a decode looks degenerate, retry hotter instead
#                                     of emitting the loop.
#   compression_ratio_threshold     - detects repetitive output (loops compress well).
#   logprob_threshold               - rejects low-confidence decodes.
#   no_speech_threshold             - emits nothing rather than inventing words in silence.
ROBUST_GENERATE_KWARGS = {
    "condition_on_prev_tokens": False,
    "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    "compression_ratio_threshold": 1.35,
    "logprob_threshold": -1.0,
    "no_speech_threshold": 0.6,
}

_asr_cache = {}

# OpenVINO IR built by benchmark/convert_whisper.py. Autodetected the same way the SLM's is,
# so a machine that has run the conversion uses it with no configuration, and a machine that
# has not falls back to plain transformers instead of failing.
_OV_DIR = os.environ.get("WHISPER_OV_DIR") or str(
    Path(__file__).resolve().parent.parent / "models" / "whisper-small-ov-int8"
)


def _ov_available() -> bool:
    return Path(_OV_DIR).is_dir() and (Path(_OV_DIR) / "openvino_encoder_model.xml").exists()


def get_asr(model_name: str = DEFAULT_MODEL):
    """Load Whisper once per model name and keep it warm.

    Prefers the OpenVINO INT8 build when it has been converted on this machine. Both paths
    return a transformers `pipeline`, so every caller and all the ROBUST_GENERATE_KWARGS
    behave identically - the only thing that changes is which runtime executes the model.
    """
    if model_name in _asr_cache:
        return _asr_cache[model_name]

    from transformers import pipeline

    if model_name == DEFAULT_MODEL and _ov_available():
        try:
            from optimum.intel import OVModelForSpeechSeq2Seq
            from transformers import AutoProcessor

            model = OVModelForSpeechSeq2Seq.from_pretrained(_OV_DIR)
            processor = AutoProcessor.from_pretrained(_OV_DIR)
            _asr_cache[model_name] = pipeline(
                "automatic-speech-recognition",
                model=model,
                tokenizer=processor.tokenizer,
                feature_extractor=processor.feature_extractor,
                # device=-1 is REQUIRED, not a default. transformers otherwise auto-selects
                # MPS on Apple Silicon and hands OpenVINO an mps:0 tensor, which it cannot
                # convert ("can't convert mps:0 device type tensor to numpy"). OpenVINO does
                # its own device selection internally; torch only needs to stay on the host.
                device=-1,
            )
            return _asr_cache[model_name]
        except Exception as exc:  # noqa: BLE001 - never let an accel path break transcription
            # Deliberately broad and deliberately non-fatal. This runs seconds before someone
            # describes a medical emergency; a missing dependency or a bad IR must degrade to
            # the working CPU path, never take speech recognition down with it.
            print(f"[stt] OpenVINO unavailable ({exc}); using transformers", flush=True)

    _asr_cache[model_name] = pipeline(
        "automatic-speech-recognition", model=model_name, device=-1
    )
    return _asr_cache[model_name]


def backend_name() -> str:
    """Which runtime transcription would use - for the benchmark and the pitch."""
    return "OpenVINO INT8" if _ov_available() else "transformers (CPU fp32)"


def prepare_audio(audio_array, sampling_rate: int):
    """Mono, 16 kHz float - exactly what Whisper expects.

    We resample ourselves: transformers' automatic resampling garbled 48 kHz input
    into repeated nonsense.
    """
    import torch
    import torchaudio

    wav = torch.tensor(audio_array, dtype=torch.float32)
    if wav.ndim > 1:
        wav = wav.mean(dim=1)  # mix stereo down to one channel
    if sampling_rate != WHISPER_SAMPLE_RATE:
        wav = torchaudio.functional.resample(
            wav, orig_freq=sampling_rate, new_freq=WHISPER_SAMPLE_RATE
        )
    return wav.numpy()


def transcribe(source, language: str = None, model_name: str = DEFAULT_MODEL,
               task: str = "transcribe") -> str:
    """Transcribe a path or file-like object.

    `language` should be the caller's language code from their profile (e.g. "en", "vi",
    "zh"). Passing it removes a whole failure class - Whisper guessing wrong on short or
    accented speech. None falls back to auto-detect.

    `task`:
      "transcribe" - the caller's own words, in their own language. What they SEE and confirm.
      "translate"  - Whisper's built-in translation to English. What the CLASSIFIER reads.

    WHY BOTH (measured 2026-08-14). The classifier's prompt, few-shot examples and all 29
    trigger phrases are English. Handing it Chinese produced [] - every symptom silently
    dropped. Korean produced a FABRICATED `no_pulse`, the term that maps to immediate cardiac
    arrest. Translating first fixed both: each returned the correct collapsed + chest_pain.

    CAVEAT, and it is a real one: translate mode LOSES NEGATION. Both test clips said "there is
    no response" and both came back as the opposite. That inversion never reached the briefing
    only because consciousness is in SLM_DISCARD and comes from a forced button instead - but
    the same corruption could hit a symptom that is not excluded. The interpretation
    confirmation screen is the remaining backstop.
    """
    import soundfile as sf

    audio, sr = sf.read(source)
    audio = prepare_audio(audio, sr)

    kwargs = dict(ROBUST_GENERATE_KWARGS)
    kwargs["task"] = task
    if language:
        kwargs["language"] = language

    result = get_asr(model_name)(
        {"array": audio, "sampling_rate": WHISPER_SAMPLE_RATE},
        generate_kwargs=kwargs,
    )
    return result["text"].strip()
