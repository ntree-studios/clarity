"""Brown-corpus punctuation-context model.

For each of , ; : the model counts the (previous POS, next POS) pairs seen in Brown.
Conditioning per mark matters: semicolons are roughly 20x rarer than commas, so a
global distribution would flag every correct semicolon.

Build once at image build time: python -m clarity.punct_model
"""

from __future__ import annotations

import pickle
from functools import lru_cache
from importlib import resources
from pathlib import Path

from nltk import ConditionalFreqDist

MARKS = (",", ";", ":")
MODEL_FILE = "punct_model.pkl"
SPACY_TO_UNIVERSAL = {
    "AUX": "VERB",
    "CCONJ": "CONJ",
    "SCONJ": "CONJ",
    "PART": "PRT",
    "PROPN": "NOUN",
    "INTJ": "X",
    "SYM": "X",
    "PUNCT": ".",
}


def to_universal(pos: str) -> str:
    return SPACY_TO_UNIVERSAL.get(pos, pos)


def build_model() -> ConditionalFreqDist:
    from nltk.corpus import brown

    cfd: ConditionalFreqDist = ConditionalFreqDist()

    for sent in brown.tagged_sents(tagset="universal"):
        toks: list[tuple[str, str]] = []

        for word, tag in sent:
            if word in MARKS and toks and toks[-1][0] == word:
                continue  # Brown encodes ; as two adjacent tokens

            toks.append((word, tag))

        padded = [("<s>", "BOS"), *toks, ("</s>", "EOS")]

        for i in range(1, len(padded) - 1):
            word = padded[i][0]

            if word in MARKS:
                cfd[word][(padded[i - 1][1], padded[i + 1][1])] += 1

    return cfd


def model_path() -> Path:
    return Path(str(resources.files("clarity").joinpath("data", MODEL_FILE)))


@lru_cache(maxsize=1)
def load_model() -> ConditionalFreqDist:
    path = model_path()

    if path.exists():
        with path.open("rb") as fh:
            return pickle.load(fh)

    return build_model()


def score(mark: str, prev: str, nxt: str) -> float:
    """Occurrences per 10k of this mark that share the (prev, next) context."""
    dist = load_model()[mark]
    total = dist.N()

    return dist[(prev, nxt)] / total * 10000 if total else 0.0


def main() -> None:
    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("wb") as fh:
        pickle.dump(build_model(), fh)

    print(f"wrote {path}")


if __name__ == "__main__":
    main()
