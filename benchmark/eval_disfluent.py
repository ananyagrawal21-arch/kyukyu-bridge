"""Does classification survive PANICKED speech?

    python benchmark/eval_disfluent.py

WHY THIS EXISTS
    Accent is tested (L2-ARCTIC, real Vietnamese/Hindi speakers). PANIC never was, at any
    stage. Our own notes call slm_testset.json "optimistic vs real panicked/accented Whisper
    output" - every case in it is a clean, complete, well-formed sentence. Nobody calling 119
    about a collapsed relative speaks like that.

WHAT IT DOES
    Takes the SAME labelled cases and perturbs each transcript the way panic actually degrades
    speech, then re-scores. Same expected labels, so any drop is caused purely by the
    disfluency. Deterministic (seeded) so runs are comparable.

    This is a LOWER BOUND, not the real thing: we are perturbing text, whereas real panic also
    degrades the AUDIO before Whisper ever sees it. Passing here does not prove robustness;
    failing here proves fragility.
"""
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ontology import load_ontology  # noqa: E402
from slm_classify import classify  # noqa: E402

DEFAULT_TESTSET = Path(__file__).resolve().parent / "slm_testset.json"

# Filler and self-interruption, drawn from how distressed callers actually speak.
FILLERS = ["oh god", "please", "oh my god", "help", "please hurry", "I don't know"]


def stutter(word: str) -> str:
    """he -> he- he"""
    return f"{word}- {word}"


def perturb(text: str, rng: random.Random) -> str:
    """Apply the three things panic does to speech: filler, repetition, false starts."""
    words = text.split()
    if len(words) < 4:
        return text

    # 1. Repeat a content word ("his chest, his chest")
    i = rng.randrange(len(words))
    words.insert(i + 1, words[i])

    # 2. Stutter an early word
    j = rng.randrange(min(3, len(words)))
    words[j] = stutter(words[j])

    out = " ".join(words)

    # 3. Bracket with panic filler
    out = f"{rng.choice(FILLERS)}, {out}, {rng.choice(FILLERS)}"
    return re.sub(r"\s+", " ", out).strip()


def score(cases, transform, ont, label):
    tp = fp = fn = exact = 0
    damage = []
    for c in cases:
        expected = set(c["expected"])
        text = transform(c["transcript"])
        pred = set(classify(text, ont)) - set(c.get("acceptable", []))
        tp += len(pred & expected); fp += len(pred - expected); fn += len(expected - pred)
        if pred == expected:
            exact += 1
        else:
            damage.append((text, sorted(expected), sorted(pred)))
    n = len(cases)
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    print(f"\n--- {label} ---")
    print(f"  exact {exact}/{n} ({100*exact/n:.0f}%)  precision {prec:.2f}  "
          f"recall {rec:.2f}  F1 {f1:.2f}  fabrications {fp}")
    return {"exact": exact, "prec": prec, "rec": rec, "f1": f1, "fp": fp}, damage


def main():
    testset = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TESTSET
    cases = json.loads(testset.read_text(encoding="utf-8"))["cases"]  # see ontology.py note
    ont = load_ontology()
    rng = random.Random(0)  # seeded: comparable between runs

    print(f"{testset.name}: {len(cases)} cases")
    print("\nExample perturbation:")
    print(f"  before: {cases[0]['transcript']}")
    print(f"  after : {perturb(cases[0]['transcript'], random.Random(0))}")

    clean, _ = score(cases, lambda t: t, ont, "CLEAN (baseline)")
    noisy, damage = score(cases, lambda t: perturb(t, rng), ont, "PANICKED (perturbed)")

    print("\n--- damage ---")
    for key in ("exact", "prec", "rec", "f1"):
        d = noisy[key] - clean[key]
        print(f"  {key:5}: {clean[key]:.2f} -> {noisy[key]:.2f}  ({d:+.2f})")
    print(f"  fabrications: {clean['fp']} -> {noisy['fp']}   <- most safety-critical")

    if damage:
        print("\n--- cases broken by disfluency ---")
        for text, exp, got in damage[:10]:
            print(f"  {text!r}\n      expected {exp}  got {got}")


if __name__ == "__main__":
    main()
