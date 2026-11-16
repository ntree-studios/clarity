# Rule schema

A rule is one YAML mapping under `rules:` in a `.yml` file inside a `rules/` folder of a config
directory (`.clarity/` in a project, or the user directory). Rules merge by `id`: a rule with a
known id overrides only the fields it sets, a new id adds a rule.

## Required

| field | meaning |
|---|---|
| `id` | unique slug, lowercase with hyphens |
| `category` | a category id such as `hedges` (see `clarity://categories`) or its number |

## Common

| field | values | default |
|---|---|---|
| `severity` | `info`, `warning`, `error` | `warning` |
| `confidence` | `exact`, `inferred` | `exact` |
| `message` | text shown with each finding | empty |
| `description` | what the rule detects and why it is a problem for the reader | empty |
| `remediation` | how to fix a finding; every finding carries it | empty |
| `count_scope` | `document`, `section`, `paragraph`, `sentence`, `clause` | `document` |
| `max_per_1k` | allowed matches per 1,000 words. Only with `count_scope: document` | 0 |
| `max_per_scope` | allowed matches per unit. Only with a scope other than `document` | 0 |
| `position` | `anywhere`, `sentence-initial`, `clause-initial`, `sentence-final`, `paragraph-final`, `section-final` | `anywhere` |
| `applies_to` | the section fields the rule reads: any of `title`, `subtitle`, `text`, `items` | all four |
| `experimental` | report findings but never score them. Skips the fixture requirement | false |

Setting `max_per_1k` with a non-document scope, or `max_per_scope` with the document scope, is a
load error that reports the rule id.

`params: {whole_field: true}` keeps a match only when it covers its whole title, subtitle,
paragraph or item, apart from closing punctuation. `count-noun-title` uses it so "Ten topics" fires
and "Ten topics we cover today" does not.

`applies_to` matters for section trees (see `clarity://guide/document`). A plain string is all
`text`. Rules that judge full sentences (length, run-ons, comma splices) read `[text]` only,
because titles, subtitles and items are fragments by design. A rule for titles reads `[title]`.

## Backends

`backend: phrase` (default). Fields: `phrases` (matched on lemmas unless `match: lower`),
`lower_phrases` (surface form, case-folded), `pattern` (a spaCy Matcher token pattern),
`match: lemma | lower`.

```yaml
- id: corporate-verbs
  category: corporate-vocabulary
  max_per_1k: 0
  phrases: [leverage, unlock, empower]
```

`backend: dependency`. Fields: `patterns` (spaCy DependencyMatcher patterns), `anchor` (the
pattern node the finding spans), `concreteness_max`, `suppress_if` (see below),
`next_lemma`.

`backend: structural`. Fields: `function` (a registered Python function) and `params`. Built-in
functions include `escalation_window`, `rule_of_three`, `consecutive_fragments`,
`question_answer`, `section_restatement`, `sentence_restatement`, `redundant_closer`,
`hedge_stacking`, `long_sentence`, `repeated_ngram`, `figurative_cost`. A new function needs code;
YAML can only configure existing ones.

`function: query` needs no code. It reads a record set (see `records` in `clarity://surface`):
paragraphs, sections, topic chunks, segments, topics, sections and graph nodes and edges.

```yaml
- id: long-digression
  category: topic-structure
  backend: structural
  function: query
  experimental: true
  message: A digression of {words} words.
  params:
    records: topics.segments
    where:
      - {field: kind, op: eq, value: digression}
      - {field: words, op: gt, value: 150}
    requires: {key: n_chunks, gte: 8}
```

`where` conditions are `{field, op, value}` with op `lt`, `lte`, `gt`, `gte`, `eq`, `ne`, `in`,
`not_in` or `contains`; `match: any` joins them with or. `aggregate: {measure: count|share, op,
value}` fires once when the count or word share of matches passes. `params.topics` changes topic
settings for this rule only. Profiles can carry rules too, under `rules:`, with fixtures in
`profiles/<name>.test.yml`.

## Fixtures

Every rule that is not `experimental: true` needs fixtures: at least one `should_fire` and two
`should_not_fire` cases. See `clarity://schema/fixture`. Rules written by `write_rules` start
experimental and lose the flag when `write_fixtures` succeeds.

## Numeric thresholds you can tune

`max_per_1k`, `max_per_scope`, and under `params`: `jaccard`, `max_new_content_lemmas`,
`max_words`, `window`, `chain_length`, `min_occurrences`, `min_words_apart`, `key_term_min`.
Switches for `repeated_ngram`: `skip_compounds` (true/false) and `report` (each/first).
