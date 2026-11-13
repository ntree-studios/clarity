"""The three bootstrap prompts. Each states that clarity measures every number."""

from __future__ import annotations

from clarity.bootstrap import RATIO_FLOOR
from clarity.corpus import HARD_DOCS, HARD_WORDS, RELIABLE_DOCS, RELIABLE_WORDS

MEASUREMENT_RULE = """\
Measurement rule. You propose; clarity measures. Every number you cite (document counts, word
counts, hit rates, ratios) must come from a clarity tool call in this session. Do not propose a
rule you have not measured. Do not present a ratio you did not receive from a tool call. Do not
write rules from general knowledge of bad writing. A proposed rule is a hypothesis until
test_rule has run it against both corpora."""


def bootstrap_rules(good: str, bad: str, focus: str) -> str:
    hint = f"\nThe user asked to focus on: {focus}. Prefer candidates there.\n" if focus else ""

    return f"""\
Build a measured rule pack from two folders of writing.
Good corpus (writing the user approves of): {good}
Bad corpus (writing the user wants to catch): {bad}
{hint}
{MEASUREMENT_RULE}

Steps:

1. Call corpus_stats on both paths. Report document count, word count and reliability for each.
   Corpus floors: under {HARD_DOCS} documents or {HARD_WORDS:,} words in either corpus, stop and
   say so, with the reason: a ratio from so little writing is noise, and the tools refuse it.
   Between that and {RELIABLE_DOCS} documents or {RELIABLE_WORDS:,} words, continue but mark every
   ratio provisional and say they need more data. At or above both, ratios are reliable.
2. Call suggest_rules with both paths. It ranks n-grams by log-odds between the corpora. If it
   returns nothing useful, say so. Do not invent candidates.
3. Read a sample of documents from each corpus so you can interpret the candidates. A bare
   n-gram list needs grouping a reader can follow.
4. Read clarity://schema/rule and clarity://guide/authoring before drafting YAML.
5. Group candidates into categories with a name and one sentence of description.
6. For each group draft one rule definition and call test_rule with it and both paths. Report the
   good rate, bad rate and ratio exactly as returned.
7. Discard every rule with a ratio under {RATIO_FLOOR:g} and say so by name with its ratio.
   Never drop a rule silently.
8. Show the surviving rules to the user as YAML with the measured ratios attached. Ask accept
   or reject for each rule.
9. Call write_rules only for accepted rules, with user_approved true, passing the exact
   definitions you measured. A definition that differs from the one you measured is refused.
   Writes go to the working directory's .clarity folder unless the user asks for target user.
10. Finish with a summary that lists every kept rule with its ratio, every discarded rule with
    its ratio and why, and the path written. Say the rules are experimental (reported,
    unscored) until fixtures exist, and offer /bootstrap_fixtures for each rule.
"""


def bootstrap_fixtures(rule_id: str) -> str:
    return f"""\
Write fixtures for the rule {rule_id}. A rule without negative cases is the rule that gets the
tool uninstalled, so negative cases matter more than positive ones. The minimum is 1 should_fire
and 2 should_not_fire.

{MEASUREMENT_RULE}

Steps:

1. Call get_rule for {rule_id}. Read clarity://schema/fixture.
2. Ask the user for the good and bad corpus paths if you do not have them.
3. Call find_matches on the bad corpus to retrieve real sentences the rule fires on. Propose
   should_fire cases from those hits, not from sentences you invent.
4. Call find_matches on the good corpus. Show the user any hits and ask which are acceptable
   writing. Confirmed ones become should_not_fire cases.
5. Propose should_not_fire cases covering: a near miss that differs from a positive by one token,
   and a legitimate use of the same vocabulary. Write these yourself, then check them in step 6.
6. Call validate_fixtures with the full set. Fix any failing case: a failing should_not_fire
   means the rule is too broad, so tell the user rather than deleting the case.
7. Show the user the exact fixtures. On acceptance call write_fixtures with user_approved true.
   The rule leaves experimental once the fixtures are written.
"""


def tune_rule(rule_id: str) -> str:
    return f"""\
Tune the rule {rule_id}, which fires too often or not enough.

{MEASUREMENT_RULE}

Steps:

1. Call get_rule for {rule_id}. Find its numeric thresholds: params such as jaccard,
   max_new_content_lemmas and max_words, plus concreteness_max, max_per_1k and max_per_scope.
2. Ask the user for the good and bad corpus paths if you do not have them.
3. Pick one threshold. Call test_rule once per value across a sweep of at least five values,
   changing only that field of the definition. Do not estimate between values.
4. Present the curve as a table: value, good rate, bad rate, ratio, documents hit.
5. Recommend one value and state the tradeoff with the measured numbers: what it catches that
   the next value misses, and what it flags on the good corpus that the next value does not.
6. If the user accepts, show the exact definition and call write_rules with user_approved true.
   A ratio under {RATIO_FLOOR:g} is refused.
"""


def bootstrap_composites(good: str, bad: str) -> str:
    return f"""\
Find composite rules: co-occurrences of existing rules that separate two folders of writing
better than either rule alone.
Good corpus: {good}
Bad corpus: {bad}

{MEASUREMENT_RULE}

Steps:

1. Call corpus_stats on both paths and apply the corpus floors from bootstrap_rules. Under the
   hard floor, stop and say why.
2. Read clarity://schema/composite and clarity://rules. Read a sample of documents from each
   corpus to see which compound tells recur.
3. Draft composites that pair rules from the pack (requires_all, requires_any, requires_none,
   with min_count where a repeat matters) in a scope where the pair reads as one tell.
4. For each draft call test_composite with both paths. Report the composite ratio and the ratio
   of every member exactly as returned.
5. Propose a composite only when beats_members is true: its ratio must beat each member's. Say
   plainly which drafts failed and why, with the numbers. Never drop one silently.
6. Show the survivors as YAML with the measured ratios. On acceptance call write_rules with
   user_approved true and the exact definitions you measured, then offer /bootstrap_fixtures.
   A composite needs a fixture with both members present and one with a single member.
"""
