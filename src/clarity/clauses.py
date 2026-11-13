"""Clause segmentation, built once.

spaCy provides no clause boundaries. Hedge stacking, the clause-initial position filter,
clause overload and the comma-splice and run-on rules all need them, so they share this one
definition of what a clause is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spacy.tokens import Doc, Span, Token

SUBJECT_DEPS = {"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"}
VERBAL = {"VERB", "AUX"}


def is_clause_head(tok: Token) -> bool:
    """A finite clause head: a verb or auxiliary carrying its own subject.

    A non-finite complement such as the 'run' in 'decided to run' has no subject child, so it
    is not a head and stays inside the clause of 'decided'.
    """
    return tok.pos_ in VERBAL and any(c.dep_ in SUBJECT_DEPS for c in tok.children)


@dataclass(frozen=True)
class Clause:
    """One clause: its head and the tokens it owns.

    Tokens are the head's subtree minus the subtrees of nested clause heads, so they are not
    always contiguous (a relative clause sits inside its matrix clause).
    """

    head: Token
    tokens: list[Token] = field(compare=False)

    @property
    def start(self) -> int:
        return self.tokens[0].i

    @property
    def end(self) -> int:
        return self.tokens[-1].i

    @property
    def span(self) -> Span:
        """The bounding span, including any nested clause."""
        return self.head.doc[self.start : self.end + 1]

    @property
    def first(self) -> Token:
        """First non-punctuation token, which is what position: clause-initial tests."""
        return next((t for t in self.tokens if not t.is_punct and not t.is_space), self.tokens[0])


def _sentence_tokens(sent: Span) -> list[Token]:
    return [t for t in sent if not t.is_space]


def _owner(tok: Token, heads: set[int]) -> int:
    node = tok

    while node.i not in heads and node.head.i != node.i:
        node = node.head

    return node.i


def clauses(doc: Doc) -> list[Clause]:
    """Finite clauses as token groups in document order, non-overlapping.

    A sentence whose root is not a verb yields a single clause covering the sentence, which is
    also what the fragment detector keys on. So does a verb root with no subject (an imperative)
    when it has no finite clause inside it.
    """
    out: list[Clause] = []

    for sent in doc.sents:
        tokens = _sentence_tokens(sent)

        if not tokens:
            continue

        root = sent.root

        if root.pos_ not in VERBAL:
            out.append(Clause(root, tokens))

            continue

        heads = {t.i for t in tokens if is_clause_head(t)} | {root.i}
        groups: dict[int, list[Token]] = {h: [] for h in heads}

        for tok in tokens:
            groups[_owner(tok, heads)].append(tok)

        out.extend(Clause(doc[h], toks) for h, toks in groups.items() if toks)

    return sorted(out, key=lambda c: c.start)
