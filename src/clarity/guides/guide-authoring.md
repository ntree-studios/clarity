# Authoring guide

## How a rule runs

1. The text is masked: code fences, tables, inline code, URLs, HTML and markdown markers are
   blanked so they are not read as prose.
2. The backend finds matches.
3. `position` filters matches. A match failing the position test is not a finding and uses no
   allowance.
4. Matches are counted in units set by `count_scope`.
5. Matches beyond the allowance are over allowance and cost score. Matches within it are reported
   but free.

## Choosing a backend

| the pattern is | use |
|---|---|
| specific words or phrases | `phrase` |
| a grammatical relation (subject, object, modifier) | `dependency` |
| a property of a sentence, paragraph or document that needs code | `structural` with an existing function |

Start with `phrase`. A word list measured against both corpora is the cheapest honest rule.

## Scopes and allowances

`count_scope: document` uses `max_per_1k`. Other scopes use `max_per_scope`. An allowance of 0
means every match costs score. Use a positive allowance for habits that are fine in moderation.

`section` scope and `position: section-final` need markdown headings; on plain text those rules
are disabled and the report says so. `paragraph-final` and `count_scope: paragraph` use blank-line
separated blocks.

## Severity and confidence

`confidence: exact` means a match is the thing named. `confidence: inferred` means a match is
probably the thing; users can filter inferred findings with `--min-confidence exact`. Lexical
rules about meaning (restatement, closers) are inferred.

## Workflow

1. `corpus_stats` on both folders. 2. `suggest_rules`. 3. Read documents to group candidates.
4. Draft a rule per group. 5. `measure` it with `test_rule`. 6. Keep ratios of 3.0 or more.
7. `write_rules`, then `bootstrap_fixtures` for each rule, then `write_fixtures`.

Never state a hit rate or ratio you did not receive from a tool call.
