"""NLI-8 step C — learner version of the fine-tune script.

Teaches the meaning-checker on our training sentences. Same behaviour as
before: 90/10 sentence split, same pair rules, same seeds, same save path.
Read KNOBS, then STEP 1 through STEP 9 top to bottom.
"""
import json
import random
from collections import Counter
from pathlib import Path

import torch
from torch.optim import AdamW
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ---------------------------------------------------------------------------
# KNOBS — the only numbers you should turn. Defaults match the real training
# run. Change one at a time, then look at the printout.
# ---------------------------------------------------------------------------
EPOCHS = 3                    # more = more passes over the data; too many and it memorizes
LEARNING_RATE = 2e-5          # bigger = bigger weight updates each step; too big and it can unlearn
BATCH_SIZE = 8                # how many pairs the model sees at once; bigger uses more memory
NEUTRALS_PER_SENTENCE = 3     # extra "not this symptom" pairs per sentence; more = more "neither" practice
HOLD_BACK = 0.1               # fraction of SENTENCES kept off training to check if it learned; 0.1 = 10%
SEED = 42                     # locks the shuffle so a rerun with the same knobs gives the same pairs
DRY_RUN = False               # True = build pairs, print counts and 5 examples, stop before loading the model

# If the true symptom is A, these are the easy mix-ups we also show as "not this".
# Change a line and those two symptoms get practised as lookalikes; remove a line and they don't.
LOOKALIKE = {
    "headache": ["palpitations"],
    "palpitations": ["headache"],
    "numbness": ["one_sided_weakness"],
    "one_sided_weakness": ["numbness"],
    "cold_sweat": ["body_cold", "pale_complexion"],
    "body_cold": ["cold_sweat", "pale_complexion", "drowning"],
    "pale_complexion": ["cold_sweat", "body_cold"],
    "choking": ["nausea", "vomiting", "difficulty_breathing"],
    "nausea": ["choking", "dizziness"],
    "vomiting": ["choking"],
    "difficulty_breathing": ["choking"],
    "seizure": ["back_pain", "high_fever"],
    "back_pain": ["seizure", "lower_back_pain"],
    "high_fever": ["seizure"],
    "collapsed": ["fall", "fall_down"],
    "fall": ["collapsed", "fall_down"],
    "fall_down": ["collapsed", "fall"],
    "chest_pain": ["severe_abdominal_pain"],
    "severe_abdominal_pain": ["chest_pain"],
    "lower_back_pain": ["back_pain"],
    "dizziness": ["nausea"],
    "drowning": ["body_cold"],
}

# Fixed paths and model name — not knobs. The checker we start from, and where we save.
ROOT = Path(__file__).resolve().parent.parent
TRAIN_PATH = ROOT / "data" / "nli_train_sentences.json"
HYPO_PATH = ROOT / "data" / "nli_hypotheses.json"
SAVE_DIR = ROOT / "models" / "nli-mdeberta-ft"
MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
MAX_LEN = 128
WEIGHT_DECAY = 0.01


def build_pairs(sentences, hypotheses):
    """Turn each caller sentence into labelled pairs: yes / no / not-this."""
    ids = list(hypotheses)
    pairs = []
    for sent in sentences:
        expected = list(sent.get("expected") or [])
        denied = list(sent.get("denied") or [])
        banned = set(expected) | set(denied)
        transcript = sent["transcript"]

        for sid in expected:
            if sid in hypotheses:
                pairs.append((transcript, hypotheses[sid], "entailment"))
        for sid in denied:
            if sid in hypotheses:
                pairs.append((transcript, hypotheses[sid], "contradiction"))

        # Neutral: lookalikes of the expected ids first, then random, never banned.
        neutrals = []
        seen = set()
        for sid in expected:
            for lookalike in LOOKALIKE.get(sid, []):
                if lookalike in hypotheses and lookalike not in banned and lookalike not in seen:
                    neutrals.append(lookalike)
                    seen.add(lookalike)
        leftover = [i for i in ids if i not in banned and i not in seen]
        random.shuffle(leftover)
        neutrals.extend(leftover)
        for sid in neutrals[:NEUTRALS_PER_SENTENCE]:
            pairs.append((transcript, hypotheses[sid], "neutral"))
    return pairs


def tokenize_pairs(tokenizer, pairs, label2id):
    """Turn text pairs into the number grids the model trains on."""
    caller_texts = [p[0] for p in pairs]
    hypo_texts = [p[1] for p in pairs]
    label_numbers = torch.tensor([label2id[p[2]] for p in pairs])
    encoded = tokenizer(
        caller_texts,
        hypo_texts,
        max_length=MAX_LEN,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    )
    encoded["labels"] = label_numbers
    return encoded


if __name__ == "__main__":

    # STEP 1 — load the two JSON files.
    # The sentences are what callers say, plus the right answers. The hypotheses
    # are the fixed "The person has …" lines. We skip keys starting with "_"
    # because that is a note, not a symptom.
    sentences = json.loads(TRAIN_PATH.read_text(encoding="utf-8"))["sentences"]
    raw_hypotheses = json.loads(HYPO_PATH.read_text(encoding="utf-8"))
    hypotheses = {k: v for k, v in raw_hypotheses.items() if not k.startswith("_")}

    # STEP 2 — split by SENTENCE, not by pair.
    # If two pairs from the same sentence landed in both train and held-back,
    # the score would cheat: the model would have already seen that wording.
    # SEED locks the shuffle so the split is the same every run.
    random.seed(SEED)
    sentences = list(sentences)
    random.shuffle(sentences)
    split_at = int(len(sentences) * (1 - HOLD_BACK))
    train_sents = sentences[:split_at]
    hold_sents = sentences[split_at:]

    # STEP 3 — build (caller sentence, hypothesis sentence, label) pairs.
    # expected → "yes this matches" (entailment).
    # denied → "no / that was in the past" (contradiction).
    # then up to NEUTRALS_PER_SENTENCE lookalikes or random ids → "neither".
    train_pairs = build_pairs(train_sents, hypotheses)
    hold_pairs = build_pairs(hold_sents, hypotheses)

    # STEP 4 — print how many of each label we built, then maybe stop.
    # You want a mix of all three. If DRY_RUN is on, print 5 examples so you can
    # read them, and do not download or train the model.
    train_counts = Counter(p[2] for p in train_pairs)
    hold_counts = Counter(p[2] for p in hold_pairs)
    print(
        f"train: entailment={train_counts['entailment']}  "
        f"contradiction={train_counts['contradiction']}  "
        f"neutral={train_counts['neutral']}  total={len(train_pairs)}"
    )
    print(
        f"held-back: entailment={hold_counts['entailment']}  "
        f"contradiction={hold_counts['contradiction']}  "
        f"neutral={hold_counts['neutral']}  total={len(hold_pairs)}"
    )
    if DRY_RUN:
        print("\n5 example pairs:")
        for caller, hypo, label in train_pairs[:5]:
            print(f"  [{label}] {caller!r} -> {hypo!r}")
        print("DRY_RUN: stopping before the model loads.")
        raise SystemExit(0)

    # STEP 5 — load the original checker from Hugging Face.
    # Label numbers come from the model (label2id). We do not type 0/1/2 in by
    # hand, because a different checkpoint might number them differently.
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID)
    label2id = {name: int(i) for name, i in model.config.label2id.items()}

    # STEP 6 — tokenize every pair the same way.
    # The model only reads numbers. max_length=128, pad short pairs, cut long ones.
    train_enc = tokenize_pairs(tokenizer, train_pairs, label2id)
    hold_enc = tokenize_pairs(tokenizer, hold_pairs, label2id)

    # STEP 7 — pick the device and the optimiser.
    # mps = this Mac's GPU if PyTorch can use it, else the CPU. AdamW is the
    # update rule. torch.manual_seed makes the training shuffle repeatable.
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    torch.manual_seed(SEED)
    model.to(device)
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)

    # STEP 8 — train. One epoch = one pass over every training pair.
    # Each batch: guess, measure how wrong (loss), nudge the weights (backward).
    # After each epoch we score the held-back pairs without updating — if
    # train loss falls but held-back loss rises, it is memorising, not learning.
    n_train = train_enc["labels"].size(0)
    n_hold = hold_enc["labels"].size(0)
    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_order = list(range(n_train))
        random.shuffle(train_order)
        train_loss_sum = 0.0
        train_seen = 0
        for start in range(0, n_train, BATCH_SIZE):
            idx = train_order[start:start + BATCH_SIZE]
            batch = {k: v[idx].to(device) for k, v in train_enc.items()}
            optimizer.zero_grad()
            out = model(**batch)
            loss = out.loss
            loss.backward()
            optimizer.step()
            size = batch["labels"].size(0)
            train_loss_sum += float(loss) * size
            train_seen += size
        train_loss = train_loss_sum / train_seen

        model.eval()
        hold_loss_sum = 0.0
        hold_correct = 0
        hold_seen = 0
        with torch.no_grad():
            for start in range(0, n_hold, BATCH_SIZE):
                idx = list(range(start, min(start + BATCH_SIZE, n_hold)))
                batch = {k: v[idx].to(device) for k, v in hold_enc.items()}
                out = model(**batch)
                size = batch["labels"].size(0)
                hold_loss_sum += float(out.loss) * size
                pred = out.logits.argmax(dim=-1)
                hold_correct += int((pred == batch["labels"]).sum())
                hold_seen += size
        hold_loss = hold_loss_sum / hold_seen
        hold_acc = hold_correct / hold_seen
        print(
            f"epoch {epoch}/{EPOCHS}  train_loss={train_loss:.4f}  "
            f"hold_loss={hold_loss:.4f}  hold_acc={hold_acc:.4f}"
        )

    # STEP 9 — save the trained model and tokenizer.
    # Next you convert this folder to OpenVINO. Nothing here is the shipped app yet.
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(SAVE_DIR)
    tokenizer.save_pretrained(SAVE_DIR)
    print(f"saved to {SAVE_DIR}")
