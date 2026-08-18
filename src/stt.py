"""Speech-to-text - the single source of truth for both the CLI and the app.

Robustness settings target the two failures we actually observed:
  1. Whisper hallucinating repeated filler on quiet/disfluent audio
     (a real clip once produced "You're free to go." x70).
  2. Language auto-detection going wrong on short or accented speech, which
     corrupts the whole transcript. We know the caller's language from their
     profile, so we tell Whisper instead of letting it guess.
"""
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


def get_asr(model_name: str = DEFAULT_MODEL):
    """Load Whisper once per model name and keep it warm."""
    if model_name not in _asr_cache:
        from transformers import pipeline
        _asr_cache[model_name] = pipeline(
            "automatic-speech-recognition", model=model_name, device=-1
        )
    return _asr_cache[model_name]


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
