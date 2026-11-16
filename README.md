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
clarity check [path|-] [--format text|json] [--config path]... [--profile name] [--fail-under 80] [--min-confidence exact|inferred] [--disable id,id]... [--enable id,id]... [--keywords a,b] [--drift-baseline name --max-drift N]
clarity score [path|-] [--disable id,id]... [--enable id,id]...
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
clarity topics [path|-] [--anchor TEXT] [--named NAME=DESCRIPTION]... [--disable id,id]... [--enable id,id]... [--keywords a,b] [--focus-named NAME=a,b]... [--format text|json] [--graph json|graphml|dot]
clarity surface [--fields|--enums|--conditions|--metrics|--functions|--categories|--mcp] [--format markdown|json]
clarity mcp
```

`--disable` and `--enable` take rule ids or category ids, repeated or comma separated. A category id stands for every rule in it. They apply after the config files and the profile. Disables go first, so `--disable structural-tics --enable em-dash` keeps only `em-dash` from that category. `--enable ease-words` turns on a rule the shipped pack leaves off. Switching off a rule also switches off the composite rules built on it. An unknown id is an error, and the message includes the id.

Exit codes: `0` pass, `1` below `--fail-under` (or outside the readability band when `fail_outside_band` is true), `2` error.

### Sections

A plain string is one section of prose. Clarity does not read markdown: `#` lines, list markers and code fences are checked as ordinary text.

Content with titles, lists or separate parts goes in as a section tree. A section has optional `id`, `title`, `subtitle`, `text` (paragraphs separated by blank lines), `items` (a list, one string per item) and child `sections`:

```yaml
title: Spring plan
text: The garden opens on April 6 with twelve new beds.
sections:
  - title: Beds
    subtitle: Twelve raised beds
    items: [Build the frames in March, Fill them with compost by April 1]
```

`clarity check deck.yml` reads a `.json`, `.yml` or `.yaml` file as a tree; `--tree` reads one from stdin. Every title, subtitle, paragraph and item starts its own sentence, and a finding never crosses from one section into another. Each section gets its own findings, score and allowances, plus a rollup score over it and every section under it, weighted by words. The document score is the root section's rollup. Findings name the section path (`"1"` is the second child section), the field (`title`, `subtitle`, `text` or `items[i]`), and the line and column inside that field. Sections with text also get their own readability and prose metrics.

`clarity://guide/document` explains how to break a deck, page or email into sections, and `clarity://schema/document` is the JSON Schema of the input and the MCP response.

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

JSON findings carry `id, rule, category, severity, confidence, message, source, section, field, line, col, span, context, over_allowance, detail?, remediation?`. JSON categories carry `id, name, found, max_per_1k, over_by, rate_per_1k, penalty, capped`. The result also has `words`, `sentences`, `section` (the section tree with each section's findings and scores), `readability`, `prose_metrics` and `disabled_rules`. The MCP tools return only the section tree, with no flat `findings` list beside it.

### Allowances and scopes

Every rule has two independent fields.

`count_scope` is the unit the allowance is measured in:

| count_scope | allowance field | meaning |
| --- | --- | --- |
| `document` (default) | `max_per_1k` | instances per 1000 words across the input |
| `section` | `max_per_scope` | count per section of a section tree |
| `paragraph` | `max_per_scope` | count per blank-line block |
| `sentence` | `max_per_scope` | count per sentence |
| `clause` | `max_per_scope` | count per clause |

`position` sets where a match must sit to count: `anywhere` (default), `sentence-initial`, `clause-initial`, `sentence-final`, `paragraph-final`, `section-final`. A match that fails the position test is not a finding and uses no allowance.

```yaml
- id: filler-transition
  count_scope: document
  position: clause-initial
  max_per_1k: 1
```

The loader rejects `max_per_1k` on a non-document scope and `max_per_scope` on a document scope, and reports the rule id. Only document scope normalizes by length; other scopes are raw counts. At document scope the allowance is rounded down for the document's length, so 1 per 1k allows 1 on a 1050-word document.

Section rules (`count_scope: section` or `position: section-final`) need a section tree. On a plain string the text report lists them in a notice and JSON lists them under `disabled_rules` with the reason.

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
| `sentence_overlap` | `document` | `mean` |
| `topic_structure` | `document` | `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits` |
| `sentence_length_variance` | `document` | `sd` |
| `lexical_diversity` | `document` | `mtld` |
| `content_word_ratio` | `document` | `ratio` |
| `given_new_ordering` | `document` | `proportion` |
| `referential_density` | `document` | `per_1k`, `mean_antecedent_distance` |
| `mean_concreteness` | `document` | `mean` |
| `paragraph_length_distribution` | `document` | `mean` |
| `novelty_rate` | `document` | `per_sentence` |
<!-- /surface:metrics -->

Novelty rate is the average number of new content lemmas per sentence, and it lists the three lowest paragraphs by line.

The example rules in `examples/metrics.yml` turn three of them into band checks through the generic `metric_band` function.

### Baselines and drift

A baseline records the mean and spread of every tracked metric across a corpus of your own writing. It needs at least 25 documents and 20,000 words, and the build stops with an error below that.

```sh
clarity baseline build ~/writing/published --name default   # writes .clarity/baselines/default.json
cat draft.md | clarity drift                                # z-scores against the baseline
clarity check draft.md --drift-baseline default --max-drift 2.5
clarity trend draft.md --rule corporate-tier-a              # the habit across snapshots
```

`drift` prints the metrics furthest from the baseline (1.5σ or more), counts the rest, and gives a drift score: the mean absolute z across all metrics. A drift score is a distance from the baseline. A document you wrote differently on purpose should drift. The gate is off unless you pass `--max-drift`, which exits 1 above the score.

`clarity snapshot` appends a row of history per document (score, rule hits, metrics). `trend` shows a rule or metric across that history, then the current text. Given a folder, it analyzes successive drafts oldest first.

### Topics and topic shifts

`clarity topics` splits a document into chunks, joins similar chunks in a weighted graph and reads the topics off that graph. It reports the number of topics, each topic's share of the words, its distinctive terms and its most central chunk, the share of the text on the main topic, and the runs of text in order. A run is `main` (on the main topic), `digression` (off the main topic, which returns later) or `drift` (off the main topic, which never returns). Every position is a line number.

```sh
clarity topics essay.md --anchor "How to pull a good espresso shot"
clarity topics essay.md --named "finance=mortgage loan interest payment bank" --format json
clarity topics essay.md --graph graphml > essay.graphml
```

The method is a port of the topicdrift.py proof of concept:

1. Chunk. Split on blank lines and merge any chunk under 25 words into the next one.
2. Vectorize. One TF-IDF vector per chunk (scikit-learn, English stop words, words and two-word phrases, terms in at least 2 chunks, sublinear term frequency).
3. Graph. Link each chunk to its 6 most similar chunks, drop similarities under 0.03, and add 0.1 between consecutive chunks.
4. Topics. Greedy modularity communities (Clauset-Newman-Moore, NetworkX). Below a modularity of 0.2 the text is one topic. A community of 1 chunk is unassigned.
5. Labels. Class-based TF-IDF terms per topic, and the chunk with the most edge weight inside its topic.
6. Alignment. An absorbing random walk from each chunk to named topics or a "none" sink.
7. Segments. A majority vote over 3 chunks smooths the labels; runs of one label are classified against the main topic.

The main topic is the one closest to the anchor, else the largest. By default the anchor is the document's title: the root section's title, else the first section title. `--anchor` or `topics.anchor` sets literal text, and `topics.anchor: none` turns the anchor off. The report gives the anchor it used (`anchor`, `anchor_source`). Every chunk, segment and topic carries `anchor_alignment`: the probability that the random walk from its chunks ends at the anchor. A rule can test "far from the anchor" with it, which does not depend on which topic is largest. The run is deterministic: similarities are rounded before any comparison, every sort breaks ties on a second key, graph nodes are integer chunk indexes, input is NFC normalized with Unix line endings, and nothing samples. scikit-learn, NetworkX and NumPy are pinned.

Input shorter than `chunk.min_count` chunks (10 by default, from the proof of concept's note that below about 10 chunks there is too little data) reports `status: too_short` and no topics. Input whose chunks share no term reports `status: no_shared_vocabulary`. Neither is an error.

`--graph` prints the chunk graph with every attribute, sorted by node and edge. Nodes carry `words, line, end_line, topic, raw_topic, kind, anchor_alignment, aligned_to, named.<name>, degree, weighted_degree, within_topic_weight, between_topic_weight, betweenness, closeness, is_central`. Edges carry `weight, similarity, adjacency, kind` (`knn`, `adjacent` or `both`) and `distance` (1 / weight, used for betweenness and closeness, which are exact, not sampled). The MCP tool `analyze_topics` returns the same report, and the graph as node-link JSON when `graph` is true.

Every setting sits in the `topics:` block of `clarity.yml`, can be changed by a profile, and can be changed for one rule under `params.topics`. `clarity config --explain topics` names the file that set each value. Defaults and tuning, from the proof of concept:

| Setting | Default | Effect of raising it |
| --- | --- | --- |
| `chunk.min_words` | 25 | Larger chunks: more stable similarity, coarser shift positions |
| `chunk.unit` | `paragraph` | `paragraph` uses each paragraph and item, `section` each section, `sentences` each sentence |
| `chunk.max_words` | none | A longer unit is split at sentence ends |
| `chunk.min_count` | 10 | More texts reported as too short |
| `vectorize.min_df` | 2 | Fewer shared terms: fewer edges |
| `vectorize.ngram_min`, `ngram_max` | 1, 2 | Longer phrases counted |
| `vectorize.sublinear_tf` | true | (on or off) |
| `vectorize.stop_words` | `english` | (a list name, or null) |
| `vectorize.use_lemmas` | false | (on: vectorize spaCy lemmas) |
| `graph.k` | 6 | Denser graph: fewer, larger topics |
| `graph.min_sim` | 0.03 | Fewer weak edges: more unassigned chunks |
| `graph.adjacency` | 0.1 | Topics become more contiguous in text order |
| `graph.decimals` | 10 | Rounding of similarities before compare |
| `graph.centrality` | true | (off: skip betweenness and closeness) |
| `graph.measure_decimals` | 6 | Rounding of published graph measures |
| `communities.min_chunks` | 2 | More chunks unassigned |
| `communities.min_modularity` | 0.2 | More texts reported as single-topic |
| `communities.resolution` | 1.0 | More, smaller topics |
| `labels.top_n` | 6 | More terms per topic |
| `smoothing.window` | 3 | Short digressions are smoothed away |
| `align.sink` | 0.05 | More chunks assigned to "none" in named-topic alignment |
| `align.boost` | 3.0 | Named topics pull harder than chunk-to-chunk edges |
| `align.on_topic_min` | 0.5 | Fewer chunks count toward `anchor_share_above` (uncalibrated) |
| `anchor` | `title` | `title` (the root section's title, else the first title), `first-heading` (the first title), literal text, or `none` (largest topic) |
| `named` | `{}` | `{name: description words}` for alignment shares |
| `focus` | empty | `{keywords, description, named}`: what the text should be about (see below) |

Focus keywords give the subject the text should cover. Give them with `--keywords "a,b"` (and `--focus-named NAME=a,b`) on `topics`, `check` and `score`, with the `focus` argument of the MCP tools `analyze_topics`, `check_text` and `score_text`, or in `topics.focus`. With none, every output is unchanged. With keywords:

- Each keyword's n-grams join the TF-IDF vocabulary after the `min_df` fit, so a keyword found in one chunk, or in none, is not dropped.
- The focus description and keywords are added to the anchor text (`anchor_source` shows `title+focus`), and `focus.named` entries become named topics.
- Each chunk gets `keyword_hits` and `keywords_present`. A keyword matches on lowercased surface form or on spaCy lemma, so `grinding` matches `grind`, and a phrase matches as a phrase. Each section and the document get `keyword_hits`, `keyword_coverage` (share of keywords found at all), `keyword_chunk_share` (word share of chunks with a hit) and `missing_keywords`.

The experimental rule `focus-gap-section` uses them: a section with no keyword hits and an anchor alignment under 0.6 (an uncalibrated threshold).

Two document measures answer "how much is on topic", and they measure different things. `on_topic_share` is cluster membership: the word share of chunks in the main topic's community. `anchor_score` is similarity to the anchor: the word-weighted mean anchor alignment of all chunks. `anchor_share_above` is the word share of chunks whose anchor alignment is at least `align.on_topic_min`. Both anchor measures are null without an anchor or when the text is too short. All three are tracked scalars of the `topic_structure` metric.

The defaults were set on one test text. Known limits:

- Vocabulary matching. TF-IDF links chunks through shared words. On-topic text in different words can register as a new topic.
- Short texts. Below about 10 chunks there is little data for community detection.
- Gradual drift. If vocabulary changes slowly across many chunks, the text can register as one topic, or the boundary can fall at an arbitrary point.
- Shift resolution. A shift shorter than one chunk is invisible. With a window of 3, a one-chunk digression is smoothed away unless the tie rule keeps it.
- English only. The stop-word list is English.
- Flattened text. A document with no blank lines is one paragraph chunk; use `chunk.unit: sentences` for it.

## MCP

`clarity mcp` serves over STDIO. Logs go to stderr.

Every tool uses the same config as the CLI in the server's working directory: the shipped rules and profiles, then `~/.clarity` and the project `.clarity/`. `clarity mcp --config <path>` (repeatable) points the server at your own rules instead, and `--profile <name>` sets the profile every call uses. A client can set the same with the `CLARITY_CONFIG` (paths joined by `:`) and `CLARITY_PROFILE` environment variables. `check_text` and `score_text` take a `profile` argument (`"none"` for no profile) that overrides the server's. `check_text`, `score_text` and `analyze_topics` take `disable` and `enable`, lists of rule ids or category ids that work like the CLI flags of the same names.

A client checking someone else's writing should read `clarity://guide/usage` first. It has notes on the input shape and the profile, on rules to switch off for some kinds of text, and on reading the findings.

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
- **Tools:** `check_text`, `score_text`, `analyze_topics`, `list_rules`, `accept_finding`, `corpus_stats`, `suggest_rules`, `test_rule`, `find_matches`, `get_rule`, `get_metrics`, `build_baseline`, `measure_drift`, `test_composite`, `validate_fixtures`, `write_rules`, `write_fixtures`
- **Prompts:** `bootstrap_rules`, `bootstrap_composites`, `bootstrap_fixtures`, `tune_rule`
- **Resources:** `clarity://baselines`, `clarity://baselines/{name}`, `clarity://categories`, `clarity://config/resolved`, `clarity://guide/authoring`, `clarity://guide/calibration`, `clarity://guide/document`, `clarity://guide/usage`, `clarity://metrics/schema`, `clarity://profiles`, `clarity://rules`, `clarity://rules/{rule_id}`, `clarity://schema/composite`, `clarity://schema/document`, `clarity://schema/fixture`, `clarity://schema/rule`, `clarity://surface`
<!-- /surface:mcp -->

- A corpus under 10 documents or 5,000 words produces no ratio. Under 25 documents or 20,000 words, ratios are marked provisional.
- `write_rules` and `write_fixtures` need `user_approved: true`. The client may set it only after showing you the exact content.
- Writes go to the project `.clarity/rules/` folder. `target: user` writes to the user directory instead.
- Written rules start `experimental` (reported, unscored) until `write_fixtures` succeeds for them.


## Configuration

`clarity.yml` in this repository is the complete set of bundled rules: every category weight and cap, every rule and its allowance. Pass `--config` with a file that holds only your changes, or with a config directory. Rules merge by `id`. An existing id overrides the fields you set, a new id adds a rule, and `enabled: false` removes one. `disabled: true` is accepted as the same thing.

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

The shipped rule pack and the three shipped profiles sit under both. None of them is required: put `builtin: false` in any config file and clarity drops the shipped rules, watchlist and profiles and runs only yours. Categories, scoring, readability and topic settings stay, so a file of your own rules is enough.

`--config <path>` skips resolution (so does `$CLARITY_CONFIG`, when no `--config` is given). The path is a file or a directory laid out like `.clarity/`. Repeat the flag to layer several; they apply in the order given over the bundled pack. A missing path is a load error. Every run prints which files loaded and which profile is active: `config:` and `profile:` lines in text, `config_sources` and `profile` in JSON.

```
.clarity/
  clarity.yml          categories, weights, profile: <name>
  rules/*.yml          rules, any number of files, loaded alphabetically
  rules/*.test.yml     fixtures, one document per rule
  profiles/*.yml       one file per profile
  watchlist.yml        your terms
  .clarity-accept      accepted finding ids
  .clarity-snapshots/  regression baselines
```

`clarity init` fills the user directory with the bundled rules, one `rules/<category>.yml` file per category beside its `.test.yml` fixtures. It also copies the example profiles and the example rules. It never overwrites a file.

Merging is per key. For scalars, the nearest value wins. Rules merge by `id`, field by field. Lists are replaced, or edited with a suffix:

```yaml
- id: corporate-tier-a
  phrases+: [synergize]     # append to the inherited list
  phrases-: [robust]        # remove; an item that was not inherited is a load error
  enabled: false            # or turn the rule off
```

`clarity config` prints the resolved config. `clarity config --explain <rule-id>` shows which file set each field. `clarity config --validate` runs the load checks and exits 2, printing the file, rule and field of any failure.

## Profiles

A profile is a hand-written set of overrides in `profiles/<name>.yml` inside a config directory. Select one with `--profile <name>` (`none` turns profiles off) or with `profile:` in the nearest `clarity.yml`. Nothing is auto-detected. An unknown name is a load error that lists the available profiles.

Overrides apply in this order: `rules`, `disable`, `rule_override`, `allowance_multiplier`, `weight_override`, then the `readability` and `topics` blocks. A multiplier that produces a fractional allowance keeps it. For example, `max_per_1k: 0.5` on a 487-word document makes the first instance already over.

A profile can carry its own rules under `rules:`, in the same form as a rule file. They add rules or override rules by id, and exist only while the profile is active. Their fixtures go beside the profile in `profiles/<name>.test.yml`, and the usual fixture rule applies (or `experimental: true`). A profile's `topics:` block changes topic settings while it is active.

Three profiles ship with clarity and work without `clarity init`, in the CLI and the MCP server: `technical` (Google and Microsoft developer style guides), `business` (SEC Plain English Handbook, Garner, answer first) and `essay` (thesis up front, topic sentences, staying on topic). They are YAML files in `src/clarity/examples/profiles/`. A profile of the same name in `~/.clarity/profiles/`, the project `.clarity/profiles/` or a `--config` directory replaces the shipped one, and `clarity init` copies them into the user directory for editing. Every setting carries a comment that gives its source or marks it as opinion; edit them. `technical` is the only place `ease-words` is switched on (`rule_override` with `enabled: true`).

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

The mounted `/config` is the user directory, so profiles must be in `/config/profiles/`. Run `clarity init` once against a writable mount to fill it. Extra `--config` paths must be inside a mounted volume.

`.clarity-accept` and `.clarity-snapshots/` are the only paths written at runtime. They go in the working directory's `.clarity/` when it exists, so a read-only user config is safe.

## Composing rules

Four fields let a rule read other findings and metrics. Each resolves at load, and a reference that does not resolve fails with the rule and field.

- `backend: composite` with `requires_all`, `requires_any` and `requires_none` fires when other rules' findings share a scope. The members come back as `children` of one finding.
- `active_when` applies a rule only when a metric condition is true.
- `allowance_when` replaces the allowance when a metric condition holds or when another category is over its allowance.
- `suppress_if` drops a match when a token is nearby (by part of speech, lemma, entity or regex), when another rule matches in the same scope, or when a metric condition is true. A suppressed match uses no allowance.

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

### Rules from the AI-writing research

`reports/AI slop and writing rules.md` lists patterns that separate model text from human text. The default pack carries them as rules. Seven are scored because they passed calibration on the human and AI corpora (`docs/calibration.md`): `abstract-physical-verb-catalogued`, `ai-lexicon-2026`, `ai-lexicon-gpt4o`, `copula-inflation`, `generic-paragraph`, `participial-tail` and `recap-closer`. The others stay experimental (reported but unscored).

- Phrase rules: `assistant-leakage` and `template-placeholder` (chat leftovers such as "I hope this helps" and unfilled template text, severity error), `salience-frame` ("why this matters"), `engagement-bait`, `source-disclaimer`, `stiff-synonym` ("utilize", "commence"), and the AI word lists `ai-lexicon-gpt4`, `ai-lexicon-gpt4o`, `ai-lexicon-gpt5` and `ai-lexicon-2026`, each tagged with the model era its words come from. `ease-words` ("simply", "just") is off unless a profile turns it on; the technical profile does.
- Dependency rules: `participial-tail` (a trailing "-ing" clause that asserts significance), `copula-inflation` ("serves as", "stands as", "boasts") and `abstract-physical-verb` with its `-catalogued` and `-observed` variants (a physical verb such as "holds", "lands" or "tracks" on an abstract subject). The last uses the concreteness ratings and a list of programming nouns, so "The plan holds." fires and "The variable holds the count." and "The bracket holds the shelf." do not.
- Composites: `generic-paragraph` (evaluative words with no number or name), `recap-closer`, `comparison-no-verdict` and `unquantified-claim`. They read marker rules such as `number-anchor` and `name-anchor`. A marker rule (`marker: true`) feeds composites and `in_scope` and is never reported.

`hedge`, `intensifier`, `expletive-construction` and `passive-agentless` are style rules. People use them as often as AI does, and their messages describe only the style problem.

## Recommended examples

`src/clarity/examples/` holds rules that are off by default: `redundancy.yml` (two lexical rules that are noisy), `metrics.yml` (three metric band checks), `composition.yml` (two composites) and `explanation.yml` (one rule for runs of definitions, which does not separate human from GPT essays). To turn a set on, copy its `.yml` and `.test.yml` files into `.clarity/rules/` (project) or `~/.clarity/rules/` (user). `clarity init` writes them to `examples/` in the user directory, where they stay off until copied. Once they are in `rules/`, `clarity test` runs their fixtures. The starter profiles are in `src/clarity/examples/profiles/`; see [Profiles](#profiles).

- `sentence-restatement` flags a sentence whose content lemmas mostly repeat one of the previous two. Each lemma is weighted by how rare it is across paragraphs. The second sentence must be shorter, so parallel structure and sentences that develop a point stay silent. It misses restatement in different words.
- `redundant-closer` flags a paragraph's last sentence when it has 15 words or fewer and adds 3 or fewer content lemmas the paragraph has not used. It skips one-sentence paragraphs, closers that end in a colon, closers whose subject is a new noun, and closers whose new words lead into the next paragraph. Its default of 3 new lemmas comes from the target sentence, which adds 3 under spaCy (an earlier draft used 2). It did not come from corpus calibration, and on 40 human and 40 GPT essays it shows no signal (0.3x). It still flags some legitimate short closers, so run corpus mode on good writing before you trust it.

## Adding rules

A rule needs `id`, `category` (a number or slug such as `hedges`) and whatever its backend matches on. The loader rejects a rule without it, and the error gives the rule and the missing field:

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
| `applies_to` | common | ['title', 'subtitle', 'text', 'items'] |  | section fields the rule reads: title, subtitle, text, items (default all) |
| `message` | common |  |  | text shown with each finding |
| `description` | common |  |  | what the rule detects and why it is a problem for the reader |
| `remediation` | common |  |  | how to fix a finding; every finding carries it |
| `phrases` | phrase | empty | phrase: one of these | words or phrases, matched on lemmas unless match is lower |
| `lower_phrases` | phrase | empty | phrase: one of these | phrases matched on case-folded surface text |
| `pattern` | phrase | none | phrase: one of these | a spaCy Matcher token pattern, or a list of them |
| `match` | phrase | lemma |  | lemma or lower, for phrases |
| `patterns` | dependency | empty | dependency: yes | spaCy DependencyMatcher patterns |
| `anchor` | dependency | none |  | the pattern node a finding spans |
| `concreteness_max` | dependency | none |  | fire only when the governed noun rates below this (1 to 5) |
| `suppress_if` | common | empty |  | conditions that drop a match; it uses no allowance |
| `active_when` | common | none |  | metric conditions that must hold for the rule to apply |
| `allowance_when` | common | empty |  | allowances that replace the default when a condition holds |
| `requires_all` | composite | empty |  | composite: every member must have a finding in the scope |
| `requires_any` | composite | empty |  | composite: at least one member must have a finding in the scope |
| `min_any` | composite | 1 |  | composite: distinct requires_any members that must be present (default 1) |
| `requires_none` | composite | empty |  | composite: no member may have a finding in the scope |
| `note` | composite |  |  | composite: text added to the finding |
| `next_lemma` | dependency | empty |  | the match must be followed by one of these lemmas |
| `experimental` | common | False |  | report findings but leave them out of the score; skips the fixture rule |
| `fixtures_exempt` | common | False |  | skip the fixture rule (generated rules only) |
| `marker` | common | False |  | a building block: its matches feed composites and in_scope, never the report |
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
- `applies_to`: `title`, `subtitle`, `text`, `items`
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
- `query`: Findings over a record set: one per matching record, or one when an aggregate passes.
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

### Query rules over records

Measurements publish record sets: one record per chunk, segment, topic, section, graph node, graph edge or paragraph, each placed on its lines with typed fields. A `query` rule filters a record set in YAML, so a new check needs no Python. Put it in any `rules/*.yml` file or in a profile.

```yaml
rules:
  - id: finance-heavy-section
    category: topic-structure
    backend: structural
    function: query
    experimental: true
    message: "Section \"{heading}\" is mostly about finance ({named.finance})."
    params:
      records: topics.sections
      where:
        - {field: named.finance, op: gt, value: 0.5}
      requires: {key: n_chunks, gte: 6}
      topics:
        named: {finance: mortgage loan interest payment bank}
```

`where` is a list of `{field, op, value}` conditions, joined by `match: all` (default) or `any`. A condition can also be `{any: [...]}` or `{all: [...]}` over a nested list; `{field: x, op: eq, value: null}` tests for a missing value. `requires` gates the rule on the record set's summary, as in `metric_band`. With `aggregate: {measure: count|share, op, value}` the rule fires once, on the first matching record, when the count of matches (or their share of the words) passes. `detail` is a template added to the message. `{field}` placeholders work in both. `params.topics` changes topic settings for this rule only. Query rules work with `count_scope`, `position`, `suppress_if`, `active_when` and composites like any other rule. `clarity explain <rule> "text"` lists each record with its fields and the first condition it failed.

The default pack has a group of off-topic rules in the `topic-structure` category: `topic-drift` (a run off the main topic that never returns), `topic-digression` (one that returns), `off-topic-share` (over 30% of the words far from the anchor), `orphan-paragraph` (a chunk with weak links to every other chunk), `section-heading-mismatch` (a section body far from its heading), `wandering-paragraph` (a paragraph whose second half shares little with its first) and `focus-gap-section`. `clarity init` writes them to one file, `rules/topic-structure.yml`, so they can be tuned or turned off together. They count toward the score; `focus-gap-section` stays experimental because it needs focus keywords. Their thresholds were set on the planted set, since few real documents are long enough for topic analysis. `tests/planted_topics.py` builds a planted test set from the hand-written pools in `tests/topics/pools/` and scores each rule on it.

The topic record sets are empty when the topic report is not `ok` (too short, or no shared vocabulary), so topic rules stay silent on short input. The record sets, from `clarity surface --records`:

<!-- surface:records -->
Every record also has `start`, `end` and `line`. A query condition is `{field, op, value}` with op one of `lt`, `lte`, `gt`, `gte`, `eq`, `ne`, `in`, `not_in`, `contains`.

`paragraphs`: one per paragraph of a section's text (blank-line block; titles and items skip). Summary for `requires`: `count`.

| Field | Type | Meaning |
| --- | --- | --- |
| `index` | int | paragraph number |
| `words` | int | words in the paragraph |
| `sentences` | int | sentences in the paragraph |
| `opener` | str | first word, lower case |
| `first_sentence_overlap` | float | content-lemma overlap of the first sentence with the rest |
| `half_overlap` | float | content-lemma overlap of the first half of the sentences with the second |
| `ends_on_significance` | bool | the last sentence uses a records.significance phrase |
| `has_numbers` | bool | a number appears |
| `has_names` | bool | a proper noun or named entity appears |

`sections`: one per titled section, with its own text and items as the body. Summary for `requires`: `count`.

| Field | Type | Meaning |
| --- | --- | --- |
| `heading` | str | the section's title |
| `level` | int | the section's depth plus one (the root is 1) |
| `section` | str | the section's path |
| `words` | int | words in the body |
| `paragraphs` | int | paragraphs in the body |
| `heading_overlap` | float | share of the heading's content lemmas found in the body |
| `kind` | str | the first records.section_kinds entry with a word in the heading, or other |

`topics.chunks`: one per chunk of the topic graph. Summary for `requires`: `status`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits`, `n_chunks`, `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `child_sections`.

| Field | Type | Meaning |
| --- | --- | --- |
| `index` | int | chunk number in text order |
| `topic` | int | smoothed topic id; -1 is unassigned |
| `raw_topic` | int | topic id before smoothing |
| `kind` | str | main, digression or drift |
| `words` | int | words in the chunk |
| `anchor_alignment` | float | probability the walk from this chunk ends at the anchor |
| `aligned_to` | str | the named topic this chunk aligns to, or none |
| `named` | float | named.<name> is the probability of ending at that named topic |
| `terms` | list | the chunk's top TF-IDF terms |
| `end_line` | int | last line of the chunk |
| `keyword_hits` | int | focus keyword occurrences; absent without focus keywords |
| `keywords_present` | list | focus keywords found in the chunk |

`topics.edges`: one per graph edge, placed from the first chunk to the second. Summary for `requires`: `status`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits`, `n_chunks`, `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `child_sections`.

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | int | lower chunk index |
| `target` | int | higher chunk index |
| `weight` | float | total edge weight |
| `similarity` | float | cosine similarity, 0 when the edge is adjacency only |
| `adjacent` | bool | the chunks are consecutive |
| `kind` | str | knn, adjacent or both |
| `same_topic` | bool | both chunks are in one community |

`topics.nodes`: one per graph node (a chunk), with graph measures. Summary for `requires`: `status`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits`, `n_chunks`, `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `child_sections`.

| Field | Type | Meaning |
| --- | --- | --- |
| `index` | int | chunk number |
| `topic` | int | smoothed topic id |
| `raw_topic` | int | community before smoothing |
| `kind` | str | main, digression or drift |
| `words` | int | words in the chunk |
| `degree` | int | number of edges |
| `weighted_degree` | float | sum of edge weights |
| `within_topic_weight` | float | edge weight to chunks of the same community |
| `between_topic_weight` | float | edge weight to other communities |
| `betweenness` | float | exact betweenness centrality over 1/weight distances |
| `closeness` | float | closeness centrality over 1/weight distances |
| `is_central` | bool | the most central chunk of its topic |

`topics.sections`: one per titled section, measured against its own chunks. Summary for `requires`: `status`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits`, `n_chunks`, `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `child_sections`.

| Field | Type | Meaning |
| --- | --- | --- |
| `heading` | str | the section's title |
| `level` | int | the section's depth plus one (the root is 1) |
| `chunks` | int | chunks in the section |
| `words` | int | words in the section's chunks |
| `heading_alignment` | float | mean probability the walk from its chunks ends at the heading |
| `anchor_alignment` | float | word-weighted mean anchor alignment of the section's chunks |
| `main_topic_share` | float | word share of the section on the document's main topic |
| `n_topics` | int | topics present in the section |
| `section` | str | the section's path |
| `parent_alignment` | float | mean probability the walk from its chunks ends at its parent's text |
| `sibling_alignment` | float | the same, toward the text of the sections beside it |
| `parent_gap` | float | parent_alignment minus the median of its siblings'; negative is further |
| `sibling_similarity` | float | mean TF-IDF cosine between its chunks and its siblings' chunks |
| `similarity_gap` | float | sibling_similarity minus the median of its siblings' |
| `named` | float | named.<name> is the word share of the section aligned to that named topic |
| `keyword_hits` | int | focus keyword occurrences; absent without focus keywords |
| `keyword_coverage` | float | share of focus keywords found |
| `keyword_chunk_share` | float | word share of chunks with a focus keyword |
| `missing_keywords` | list | focus keywords not found |

`topics.segments`: one per run of chunks with one topic, in text order. Summary for `requires`: `status`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits`, `n_chunks`, `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `child_sections`.

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | str | main, digression or drift |
| `topic` | int | topic id of the run |
| `chunks` | int | chunks in the run |
| `words` | int | words in the run |
| `end_line` | int | last line of the run |
| `terms` | list | terms of the run's topic |
| `anchor_alignment` | float | word-weighted mean anchor alignment of the run's chunks |

`topics.topics`: one per detected topic, placed on its central chunk. Summary for `requires`: `status`, `anchor_score`, `anchor_share_above`, `keyword_coverage`, `keyword_chunk_share`, `keyword_hits`, `n_chunks`, `n_topics`, `modularity`, `on_topic_share`, `unassigned_share`, `drift_share`, `digression_count`, `child_sections`.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | int | topic id; 0 has the most words |
| `share` | float | word share of the text |
| `terms` | list | class-based TF-IDF terms |
| `central_line` | int | line of the most central chunk |
| `is_main` | bool | the main topic |
| `anchor_alignment` | float | word-weighted mean anchor alignment of the topic's chunks |
<!-- /surface:records -->

## Development

```sh
make test    # pytest and fixtures in the dev image
make lint    # ruff, mypy and jscpd duplicate detection
make docs    # rewrite the README tables that are rendered from the schema
make run ARGS="rules --category 4"
```

Categories:

<!-- surface:categories -->
1 significance-asserting, 2 discovery-narration, 3 escalation, 4 intensifiers, 5 filler-transitions, 6 corporate-vocabulary, 7 structural-tics, 8 hedges, 9 false-balance, 10 false-agency, 11 verbosity, 12 sentence-flow, 13 watchlist, 14 self-framing, 15 construction, 16 redundancy, 17 prose-metrics, 18 composite, 19 topic-structure, 20 artifacts
<!-- /surface:categories -->

Data: word ratings come from Brysbaert, Warriner and Kuperman (2014). The punctuation-context model is built from the Brown corpus.

## License

MIT. Copyright (c) 2026 N-Tree Studios. See `LICENSE`.
