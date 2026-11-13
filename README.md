# clarity

A deterministic prose linter for AI-slop writing tics. It runs as a Docker CLI and as a STDIO MCP server. The spaCy model, NLTK corpora, concreteness norms and Brown punctuation model are baked into the image.

## Install

```sh
make build            # docker build -t clarity .
```

Without Docker (Python 3.12):

```sh
pip install .
python -m spacy download en_core_web_sm
python -m nltk.downloader wordnet brown universal_tagset
python -m clarity.punct_model     # builds the pickled Brown model once
```

## CLI

```
clarity check [path|-] [--format text|json] [--config file] [--profile name] [--fail-under 80] [--min-confidence exact|inferred] [--drift-baseline name --max-drift N]
clarity score [path|-]
clarity accept <finding-id>
clarity rules [--category N]
clarity config [--explain rule-id] [--validate] [--format text|json]
clarity init
clarity test [rule|group] [--changed] [--corpus path] [--against path] [--snapshots]
clarity explain <rule-id> "text"
clarity snapshot <path>
clarity baseline build <corpus> [--name default] | list | show <name>
clarity drift [path|-] [--baseline default] [--format text|json]
clarity trend <path> [--metric name] [--rule id]
clarity repeats [path|-] [--min-occurrences 3] [--since file]
clarity surface [--fields|--enums|--conditions|--metrics|--functions|--categories|--mcp] [--format markdown|json]
clarity mcp
```

Exit codes: `0` pass, `1` below `--fail-under` (or outside the readability band when `fail_outside_band` is true), `2` error.

### Pipes

`check` and `score` read stdin when the path is `-`, or when no path is given and stdin is not a terminal. Findings name `<stdin>` as the source. Line and column count from the start of the stream.

```sh
cat draft.md | clarity check
clarity check - < draft.md
cat draft.md | docker run -i --rm clarity check
cat draft.md | docker run -i --rm clarity check --format json --min-confidence exact
```

Docker needs `-i` for piped input. Text output drops color when stdout is not a terminal or `NO_COLOR` is set.

### Output

The text report opens with the source, word count and sentence count. Each category with findings gets a header: `N found · N allowed · over by N`, or `ok` when within the allowance. Under it, one row per finding shows a marker, `line:col`, a snippet, a tag and a six-character id. Inferred findings add a detail line. After the findings come a score block (PASS or FAIL against `--fail-under` with a per-category penalty table), a readability table, the prose metrics and a footer with counts and hints.

Markers: `●` exact and over the allowance, `◐` inferred and over the allowance, `○` within the allowance.

JSON findings carry `id, rule, category, severity, confidence, message, source, line, col, span, context, over_allowance, detail?, suggestion?`. JSON categories carry `id, name, found, max_per_1k, over_by, rate_per_1k, penalty, capped`. The result also has `words`, `sentences`, `readability`, `prose_metrics` and `disabled_rules`.

### Allowances and scopes

Every rule has two independent fields.

`count_scope` is the unit the allowance is measured in:

| count_scope | allowance field | meaning |
| --- | --- | --- |
| `document` (default) | `max_per_1k` | instances per 1000 words across the input |
| `section` | `max_per_scope` | count per markdown heading block |
| `paragraph` | `max_per_scope` | count per blank-line block |
| `sentence` | `max_per_scope` | count per sentence |
| `clause` | `max_per_scope` | count per clause |

`position` says where a match must sit to count: `anywhere` (default), `sentence-initial`, `clause-initial`, `sentence-final`, `paragraph-final`, `section-final`. A match that fails the position test is not a finding and uses no allowance.

```yaml
- id: filler-transition
  count_scope: document
  position: clause-initial
  max_per_1k: 1
```

The loader rejects `max_per_1k` on a non-document scope and `max_per_scope` on a document scope, and reports the rule id. Only document scope normalizes by length; other scopes are raw counts. At document scope the allowance is rounded down for the document's length, so 1 per 1k allows 1 on a 1050-word document.

Section rules (`count_scope: section` or `position: section-final`) need markdown headings. On plain text the text report lists them in a notice and JSON lists them under `disabled_rules` with the reason.

`clarity.clauses.clauses` splits each sentence into clauses. A clause is a verb with its own subject and its words, without any clause nested inside it.

### Confidence

`exact` findings are deterministic matches. `inferred` findings rest on a heuristic such as metaphor sense, animacy or parse structure. `--min-confidence exact` hides them.

### Exemptions

`clarity accept <id>` appends the finding id to `.clarity-accept`. The id hashes the rule id, the normalized matched text and its sentence. An exemption therefore survives moved lines and works on stdin.

### Score and readability

The style score runs from 0 to 100. Each category's excess is weighted by category weight and severity, capped per category and subtracted from 100. Readability (Flesch Reading Ease, Flesch-Kincaid, Gunning Fog, SMOG, Coleman-Liau, ARI) is reported apart from the score. The reported grade is the mean of the five grade-level metrics, compared with the `readability.target_grade` band.

Prose metrics are measurements with no sentence to blame. They are printed and never scored. Each is a registered metric (`clarity.metrics`) with declared scopes, so a new measurement is one registered function. The registry, from `clarity surface --metrics`:

<!-- surface:metrics -->
| Metric | Scopes | Tracked scalars |
| --- | --- | --- |
| `sentence_type_distribution` | `sentence`, `document` | `shares.simple`, `shares.compound`, `shares.complex`, `shares.compound-complex`, `shares.fragment` |
| `subordination_index` | `sentence`, `paragraph`, `document` | `value` |
| `coordination_subordination_ratio` | `sentence`, `paragraph`, `document` | `value` |
| `clauses_per_sentence` | `sentence`, `paragraph`, `document` | `value` |
| `mean_dependency_depth` | `sentence`, `paragraph`, `document` | `value` |
| `sentence_opener_distribution` | `sentence`, `paragraph`, `document` | `distinct_share` |
| `paragraph_opener_repetition` | `document` | `value` |
| `voice_distribution` | `sentence`, `paragraph`, `document` | `passive_share` |
| `modal_density` | `sentence`, `paragraph`, `document` | `per_1k` |
| `nominal_verbal_ratio` | `sentence`, `paragraph`, `document` | `value` |
| `tense_consistency` | `document` | `shift_rate` |
| `hapax_ratio` | `sentence`, `paragraph`, `document` | `value` |
| `pronoun_antecedent_distance` | `sentence`, `paragraph`, `document` | `mean` |
| `heading_hierarchy` | `document` | `skipped_levels`, `single_child`, `empty` |
| `list_parallelism` | `document` | `mismatched` |
| `code_prose_ratio` | `document` | `value` |
| `link_density` | `document` | `per_1k` |
| `sentence_overlap` | `document` | `mean` |
| `sentence_length_variance` | `document` | `sd` |
| `paragraph_length_distribution` | `document` | `mean` |
| `lexical_diversity` | `document` | `mtld` |
| `content_word_ratio` | `document` | `ratio` |
| `given_new_ordering` | `document` | `proportion` |
| `referential_density` | `document` | `per_1k`, `mean_antecedent_distance` |
| `mean_concreteness` | `document` | `mean` |
| `novelty_rate` | `document` | `per_sentence` |
<!-- /surface:metrics -->

Novelty rate is the average number of new content lemmas per sentence, and it names the three lowest paragraphs by line.

The example rules in `examples/metrics.yml` turn three of them into band checks through the generic `metric_band` function.

### Baselines and drift

A baseline records the mean and spread of every tracked metric across a corpus of your own writing. It needs at least 25 documents and 20,000 words, and the build refuses less.

```sh
clarity baseline build ~/writing/published --name default   # writes .clarity/baselines/default.json
cat draft.md | clarity drift                                # z-scores against the baseline
clarity check draft.md --drift-baseline default --max-drift 2.5
clarity trend draft.md --rule corporate-tier-a              # the habit across snapshots
```

`drift` prints the metrics furthest from the baseline (1.5σ or more), counts the rest, and gives a drift score: the mean absolute z across all metrics. A drift score is a distance, not a verdict. A document you wrote differently on purpose should drift. The gate is off unless you pass `--max-drift`, which exits 1 above the score.

`clarity snapshot` appends a row of history per document (score, rule hits, metrics). `trend` shows a rule or metric across that history, then the current text. Given a folder, it analyzes successive drafts oldest first.

## MCP

`clarity mcp` serves over STDIO. Logs go to stderr.

Client config:

```json
{
  "mcpServers": {
    "clarity": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "clarity", "mcp"]
    }
  }
}
```

### Bootstrapping a rule pack

An AI client can build a rule pack from one folder of good writing and one folder of writing you want to catch. The client proposes and clarity measures. Every number the client reports comes from a tool call. A rule is written only if clarity measured that exact definition against both folders and its bad/good ratio is 3.0 or more.

Prompts, run from the client, for example `/mcp__clarity__bootstrap_rules <good> <bad>`:

- `bootstrap_rules(good_corpus_path, bad_corpus_path, focus?)` measures both folders, ranks candidate n-grams, drafts and tests rules, discards those under 3.0, shows the survivors and writes the ones you accept.
- `bootstrap_composites(good_corpus_path, bad_corpus_path)` finds rule co-occurrences. It proposes a composite only when its ratio beats every member's.
- `bootstrap_fixtures(rule_id)` builds fixtures from real hits in your corpora and writes them.
- `tune_rule(rule_id)` sweeps a numeric threshold and recommends a value with the measured tradeoff.

Every prompt tells the client to read `clarity://surface` first. It lists every field, enum, condition, metric and structural function a rule can use, so a draft uses what exists and the loader accepts it.

The full MCP surface, generated from the server (`clarity surface --mcp`):

<!-- surface:mcp -->
- **Tools:** `check_text`, `score_text`, `list_rules`, `accept_finding`, `corpus_stats`, `suggest_rules`, `test_rule`, `find_matches`, `get_rule`, `get_metrics`, `build_baseline`, `measure_drift`, `test_composite`, `validate_fixtures`, `write_rules`, `write_fixtures`
- **Prompts:** `bootstrap_rules`, `bootstrap_composites`, `bootstrap_fixtures`, `tune_rule`
- **Resources:** `clarity://baselines`, `clarity://baselines/{name}`, `clarity://categories`, `clarity://config/resolved`, `clarity://guide/authoring`, `clarity://guide/calibration`, `clarity://metrics/schema`, `clarity://profiles`, `clarity://rules`, `clarity://rules/{rule_id}`, `clarity://schema/composite`, `clarity://schema/fixture`, `clarity://schema/rule`, `clarity://surface`
<!-- /surface:mcp -->

- A corpus under 10 documents or 5,000 words produces no ratio. Under 25 documents or 20,000 words, ratios are marked provisional.
- `write_rules` and `write_fixtures` need `user_approved: true`. The client may set it only after showing you the exact content.
- Writes go to the project `.clarity/rules/` folder. `target: user` writes to the user directory instead.
- Written rules start `experimental` (reported, unscored) until `write_fixtures` succeeds for them.


## Configuration

`clarity.yml` in this repository is the complete set of bundled rules: every category weight and cap, every rule and its allowance. Pass `--config` with a file that holds only your changes. Rules merge by `id`. An existing id overrides the fields you set, a new id adds a rule, and `enabled: false` removes one. `disabled: true` is accepted as the same thing.

```yaml
readability:
  target_grade: [8, 12]
  fail_outside_band: false

rules:
  - {id: intensifier, max_per_1k: 3}
  - {id: hedge, enabled: false}
```

### Watchlist

Add terms without writing a rule. Findings appear under the `watchlist` category with the term as the rule id.

```yaml
watchlist:
  - {term: synergy, max_per_1k: 0}
  - {term: "load-bearing", max_per_1k: 0, match: phrase}
  - {term: bedrock, max_per_1k: 1, require_concrete_governor: true}
```

`require_concrete_governor` matches only metaphorical use. It looks up the governing or governed noun in the bundled Brysbaert ratings and fires when the rating is below 3.0.

`clarity repeats` lists phrases a draft repeats and prints them as watchlist entries.

## Where config lives

Two locations, and the nearest wins:

- `$CLARITY_HOME` (default `~/.clarity`, `/config` in the image) holds user defaults and always loads.
- The first `.clarity/` found walking up from the input file's directory overrides the user defaults. For stdin, the walk starts at the working directory.

`--config <path>` skips resolution and loads only that file over the bundled pack. Every run prints which files loaded and which profile is active: `config:` and `profile:` lines in text, `config_sources` and `profile` in JSON.

```
.clarity/
  clarity.yml          categories, weights, profile: <name>
  rules/*.yml          rules, loaded alphabetically
  rules/*.test.yml     fixtures, one document per rule
  profiles/*.yml       one file per profile
  watchlist.yml        your terms
  .clarity-accept      accepted finding ids
  .clarity-snapshots/  regression baselines
```

`clarity init` fills the user directory with the bundled rules, four example profiles and the example rules. It never overwrites a file.

Merging is per key. For scalars, the nearest value wins. Rules merge by `id`, field by field. Lists are replaced, or edited with a suffix:

```yaml
- id: corporate-tier-a
  phrases+: [synergize]     # append to the inherited list
  phrases-: [robust]        # remove; an item that was not inherited is a load error
  enabled: false            # or turn the rule off
```

`clarity config` prints the resolved config. `clarity config --explain <rule-id>` shows which file set each field. `clarity config --validate` runs the load checks and exits 2, printing the file, rule and field of any failure.

## Profiles

A profile is a hand-written set of overrides in `profiles/<name>.yml`. Select one with `--profile <name>` (`none` turns profiles off) or with `profile:` in the nearest `clarity.yml`. Nothing is auto-detected. An unknown name is a load error that lists the available profiles.

Overrides apply in this order: `disable`, `rule_override`, `allowance_multiplier`, `weight_override`. A multiplier that produces a fractional allowance keeps it. For example, `max_per_1k: 0.5` on a 487-word document makes the first instance already over.

Four examples ship: `technical`, `marketing`, `fiction` and `academic`. Each opens with a stated opinion and is meant to be edited.

## Testing rules

Rules are config, so they need tests that run on every edit. Each rule has fixtures in a `rules/*.test.yml` file beside it:

```yaml
rule: framing-noun-phrase
should_fire:
  - "The honest framing is that most advice isn't a rule."
  - {text: "The simple answer is no.", expect: {count: 1, span: "The simple answer"}}
should_not_fire:
  - "The honest broker in the deal was the escrow agent."
  - "She gave a simple answer to a simple question."
```

Write the `should_not_fire` cases first. Catching the target is easy. Leaving normal prose alone is hard, and it is why people turn linters off. The loader refuses a rule with fewer than one `should_fire` and two `should_not_fire` cases. Marking the rule `experimental: true` skips that check, reports its findings and leaves them out of the score.

```sh
clarity test                         # every fixture
clarity test framing-noun-phrase     # one rule, or a file group such as self-framing
clarity test --changed               # rules whose YAML differs from git HEAD
clarity explain <rule-id> "text"     # why a rule did or did not match, token by token
clarity test --corpus ~/writing/published/ [--corpus-ceiling 2.0]
clarity test --corpus good/ --against bad/
clarity snapshot draft.md            # record a baseline in .clarity-snapshots/
clarity test --snapshots             # diff current output against baselines
clarity test --changed --fail-on-regression
```

Corpus mode reports hits per 1000 words for each rule and flags any above the ceiling. A rule that fires that often on your best work is miscalibrated, or it describes a habit and not an error. With `--against`, the ratio of the bad corpus rate to the good corpus rate shows whether a rule separates the two. A ratio near 1.0 means it fires equally on both.

Snapshots store the findings that lower the score. The diff explains each change it can (`[new rule]`, `[allowance raised 1 → 3]`) and marks the rest `[unexplained]`. `--fail-on-regression` exits 1 on a fixture failure, a rule over the corpus ceiling or an unexplained diff.

`make test` runs pytest and the fixtures. `make test-corpus CORPUS=<path> [AGAINST=<path>]` runs corpus mode.

## Docker config

```sh
docker run -i --rm \
  -v "$HOME/.clarity:/config:ro" \
  -v "$PWD:/work" \
  -w /work \
  clarity check draft.md
```

`.clarity-accept` and `.clarity-snapshots/` are the only paths written at runtime. They go in the working directory's `.clarity/` when it exists, so a read-only user config is safe.

## Composing rules

Four fields let a rule read other findings and metrics. Each resolves at load, and a reference that does not resolve fails with the rule and field.

- `backend: composite` with `requires_all`, `requires_any` and `requires_none` fires when other rules' findings share a scope. The members come back as `children` of one finding.
- `active_when` applies a rule only when a metric condition holds.
- `allowance_when` replaces the allowance when a metric condition holds or when another category is over its allowance.
- `suppress_if` drops a match when a token is nearby (by part of speech, lemma, entity or regex), when another rule matches in the same scope, or when a metric condition holds. A suppressed match uses no allowance.

```yaml
rules:
  - id: hedged-intensifier
    category: composite
    backend: composite
    count_scope: sentence
    max_per_scope: 0
    requires_all:
      - rule: hedge
      - rule: intensifier
```

The condition forms:

<!-- surface:conditions -->
- `metric`: {metric, op, value, key?} where op is one of lt, lte, gt, gte, eq. key picks a scalar of the metric; the default is its first tracked scalar.
- `near`: suppress_if: {pos | lemma | ent | pattern, within: N} tests tokens near the match.
- `in_scope`: suppress_if: {count_scope, rule} holds when another rule matches in that scope.
- `over_allowance`: allowance_when: {over_allowance: category, <allowance field>} tightens a rule when another category is over its allowance.
- `requires`: composite members are {rule, min_count?}; one level, no composite members.
<!-- /surface:conditions -->

Composites run once, after every atomic rule, and cannot name other composites. `clarity explain <rule> "text"` shows each member's state and the suppression condition that fired. The schema is in `src/clarity/guides/schema-composite.md`.

## Recommended examples

`src/clarity/examples/` holds rules that are off by default: `redundancy.yml` (two lexical rules that are noisy), `metrics.yml` (three metric band checks), `composition.yml` (two composites) and `explanation.yml` (one rule for runs of definitions, which does not separate human from GPT essays). To turn a set on, copy its `.yml` and `.test.yml` files into `.clarity/rules/` (project) or `~/.clarity/rules/` (user). `clarity init` writes them to `examples/` in the user directory, where they stay off until copied. Once they are in `rules/`, `clarity test` runs their fixtures.

- `sentence-restatement` flags a sentence whose content lemmas mostly repeat one of the previous two. Each lemma is weighted by how rare it is across paragraphs. The second sentence must be shorter, so parallel structure and sentences that develop a point stay silent. It misses restatement in different words.
- `redundant-closer` flags a paragraph's last sentence when it has 15 words or fewer and adds 3 or fewer content lemmas the paragraph has not used. It skips one-sentence paragraphs, closers that end in a colon, closers whose subject is a new noun, and closers whose new words lead into the next paragraph. Its default of 3 new lemmas comes from the target sentence, which adds 3 under spaCy (an earlier draft said 2). It did not come from corpus calibration, and on 40 human and 40 GPT essays it shows no signal (0.3x). It still flags some legitimate short closers, so run corpus mode on good writing before you trust it.

## Adding rules

A rule needs `id`, `category` (a number or slug such as `hedges`) and whatever its backend matches on. The loader rejects a rule without it, naming the rule and the missing field:

- `phrase`: `phrases`, `lower_phrases` or `pattern`.
- `dependency`: `patterns`. `anchor` is optional.
- `structural`: `function`, one of the registered functions below.
- `composite`: `requires_all` or `requires_any`.

Every other field has a default. These are all the fields, generated from the schema (`clarity surface --fields`):

<!-- surface:fields -->
| Field | Backend | Default | Required | Meaning |
| --- | --- | --- | --- | --- |
| `id` | common | required | always | unique slug |
| `category` | common | required | always | a category id or number (see categories) |
| `backend` | common | phrase |  | how the rule matches |
| `severity` | common | warning |  | weight of a finding |
| `confidence` | common | exact |  | exact is a deterministic match; inferred rests on a heuristic |
| `max_per_1k` | common | none |  | allowed matches per 1,000 words; only at count_scope document |
| `max_per_scope` | common | none |  | allowed matches per unit; at every other count_scope |
| `count_scope` | common | document |  | the unit the allowance is counted in |
| `position` | common | anywhere |  | where a match must sit to count |
| `message` | common |  |  | text shown with each finding |
| `suggestion` | common | none |  | replacement wording shown with the finding |
| `phrases` | phrase | empty | phrase: one of these | words or phrases, matched on lemmas unless match is lower |
| `lower_phrases` | phrase | empty | phrase: one of these | phrases matched on case-folded surface text |
| `pattern` | phrase | none | phrase: one of these | a spaCy Matcher token pattern |
| `match` | phrase | lemma |  | lemma or lower, for phrases |
| `patterns` | dependency | empty | dependency: yes | spaCy DependencyMatcher patterns |
| `anchor` | dependency | none |  | the pattern node a finding spans |
| `concreteness_max` | dependency | none |  | fire only when the governed noun rates below this (1 to 5) |
| `suppress_if` | common | empty |  | conditions that drop a match; it uses no allowance |
| `active_when` | common | none |  | metric conditions that must hold for the rule to apply |
| `allowance_when` | common | empty |  | allowances that replace the default when a condition holds |
| `requires_all` | composite | empty |  | composite: every member must have a finding in the scope |
| `requires_any` | composite | empty |  | composite: at least one member must have a finding in the scope |
| `requires_none` | composite | empty |  | composite: no member may have a finding in the scope |
| `note` | composite |  |  | composite: text added to the finding |
| `next_lemma` | dependency | empty |  | the match must be followed by one of these lemmas |
| `experimental` | common | False |  | report findings but leave them out of the score; skips the fixture rule |
| `fixtures_exempt` | common | False |  | skip the fixture rule (generated rules only) |
| `function` | structural | none | structural: yes | a registered structural function (see functions) |
| `params` | structural | empty |  | values the structural function reads |
<!-- /surface:fields -->

The values each enum field accepts:

<!-- surface:enums -->
- `backend`: `phrase`, `dependency`, `structural`, `composite`
- `count_scope`: `document`, `section`, `paragraph`, `sentence`, `clause`
- `position`: `anywhere`, `sentence-initial`, `clause-initial`, `sentence-final`, `paragraph-final`, `section-final`
- `severity`: `info`, `warning`, `error`
- `confidence`: `exact`, `inferred`
- `match`: `lemma`, `lower`
- `op`: `lt`, `lte`, `gt`, `gte`, `eq`
<!-- /surface:enums -->

Pick a backend.

Phrase, the default. It uses a spaCy `Matcher` over lemmas, or over surface forms with `match: lower`:

```yaml
rules:
  - id: no-circle-back
    category: filler-transitions
    max_per_1k: 0
    severity: warning
    confidence: exact
    position: clause-initial
    message: Say what you mean.
    phrases: [circle back, touch base]
```

A raw token `pattern:` list works in place of `phrases`.

Dependency. spaCy `DependencyMatcher` patterns go under `patterns:`. `anchor` is the node to check, and `concreteness_max` is optional:

```yaml
rules:
  - id: abstract-embark
    category: corporate-vocabulary
    backend: dependency
    patterns:
      - - {RIGHT_ID: verb, RIGHT_ATTRS: {LEMMA: embark}}
        - {LEFT_ID: verb, REL_OP: ">", RIGHT_ID: obj, RIGHT_ATTRS: {DEP: pobj}}
    anchor: obj
    concreteness_max: 3.0
```

Structural. Write a Python function and register it in `src/clarity/matchers/structural.py`. Reference it with `backend: structural` and `function:`, and put tunable values under `params:`. The registered functions:

<!-- surface:functions -->
- `adjective_density`: 
- `adverb_propped_verb`: 
- `clause_overload`: Finite clauses per sentence, from the shared clause utility, when commas are present.
- `comma_splice`: 
- `compound_chain`: Runs of noun modifiers: 'quality score threshold'.
- `consecutive_fragments`: 
- `definition_chain`: A paragraph that is mostly a run of definitions, which reads as a glossary and not as
- `em_dash`: 
- `escalation_window`: 'not' + just/only within a few tokens, then a pivot (but, it, a comma) within the window.
- `expletive_construction`: 
- `figurative_cost`: 'cost' used as a figurative verb ('costs score', 'cost us credibility').
- `function_word_ratio`: 
- `hedge_stacking`: Hedges per clause. Every hedge in a clause holding min_count or more is reported.
- `intro_transition_comma`: 
- `it_depends_final`: 
- `long_sentence`: 
- `lowercase_after_terminal`: 
- `metric_band`: Fire when a registered metric crosses a threshold.
- `nested_prep_depth`: Sentences stacking prepositional phrases: of the X of the Y from the Z.
- `nominalization`: A -tion/-ment/-ance/-ence/-ity/-ness noun with a verb form, in the wordy shapes only.
- `passive_agentless`: nsubjpass plus auxpass with no 'by' phrase: the actor is missing.
- `passive_with_agent`: nsubjpass plus auxpass with a 'by' phrase: the actor is named but placed last.
- `question_answer`: 
- `rare_punctuation_context`: 
- `redundant_closer`: A short last sentence that adds few content lemmas the paragraph has not already used.
- `repeated_ngram`: A phrase the writer leans on: 3+ occurrences, spaced apart, with no proper nouns.
- `rule_of_three`: 
- `run_on_missing_comma`: 
- `section_restatement`: 
- `sentence_length_variance`: 
- `sentence_restatement`: A sentence whose content lemmas mostly repeat one of the preceding sentences.
- `stacked_adjectives`: Runs of adjectives (commas and conjunctions allowed between) before a noun.
- `subj_verb_gap`: The reader holds the subject open while a long interruption passes.
- `syllables_per_word`: 
- `two_neg_in_clause`: 
<!-- /surface:functions -->

## Development

```sh
make test    # pytest and fixtures in the dev image
make lint    # ruff, mypy and jscpd duplicate detection
make docs    # rewrite the README tables that are rendered from the schema
make run ARGS="rules --category 4"
```

Categories:

<!-- surface:categories -->
1 significance-asserting, 2 discovery-narration, 3 escalation, 4 intensifiers, 5 filler-transitions, 6 corporate-vocabulary, 7 structural-tics, 8 hedges, 9 false-balance, 10 false-agency, 11 verbosity, 12 sentence-flow, 13 watchlist, 14 self-framing, 15 construction, 16 redundancy, 17 prose-metrics, 18 composite
<!-- /surface:categories -->

Data: word ratings come from Brysbaert, Warriner and Kuperman (2014). The punctuation-context model is built from the Brown corpus.

## License

MIT. Copyright (c) 2026 N-Tree Studios. See `LICENSE`.
