# clarity

A deterministic prose linter that catches AI-slop writing tics. It ships as a Docker CLI with a STDIO MCP server mode. The spaCy model, NLTK corpora, concreteness norms and the Brown punctuation model are baked into the image. Nothing touches the network at runtime.

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
clarity check [path|-] [--format text|json] [--config clarity.yml] [--fail-under 80] [--min-confidence exact|inferred]
clarity score [path|-]
clarity accept <finding-id>
clarity rules [--category N]
clarity mcp
```

Exit codes: `0` pass, `1` below `--fail-under` (or outside the readability band when `fail_outside_band` is true), `2` error.

### Pipes

`check` and `score` read stdin when the path is `-`, or when no path is given and stdin is not a terminal. Findings report `<stdin>` as the source, with line and column offsets from the start of the stream.

```sh
cat draft.md | clarity check
clarity check - < draft.md
cat draft.md | docker run -i --rm clarity check
cat draft.md | docker run -i --rm clarity check --format json --min-confidence exact
```

`-i` is required with Docker for piped input. Text output drops color when stdout is not a terminal, or when `NO_COLOR` is set.

### Output

Text groups findings by category with a `N found · N allowed · over by N` header, then a score line and a readability line. JSON findings carry `id, rule, category, severity, confidence, message, source, line, col, span, context, over_allowance, suggestion?`. JSON categories carry `id, name, found, max_per_1k, over_by, rate_per_1k, penalty, capped`.

### Allowances

`max_per_1k` is the number of instances per 1000 words that cost nothing. Findings under the allowance are reported and score zero. Only the excess is penalized. The allowance is floored for the document length: 1 per 1k on a 1050-word document allows 1. Set `max_per_1k: 0` for zero-tolerance rules such as em dashes.

### Confidence

`exact` findings are deterministic matches. `inferred` findings rest on a heuristic (metaphor sense, animacy, parse structure). `--min-confidence exact` hides the inferred ones.

### Exemptions

`clarity accept <id>` appends the finding id to `.clarity-accept`. The id hashes the rule id and the normalized matched text with its sentence, so an exemption survives moved lines and works on stdin.

### Score and readability

The style score is 0 to 100: each category's excess is weighted by category weight and severity, capped per category, and subtracted from 100. Readability (Flesch Reading Ease, Flesch-Kincaid, Gunning Fog, SMOG, Coleman-Liau, ARI) is reported separately and never folded into the score. The `grade` is the mean of the five grade-level metrics, compared with the `readability.target_grade` band.

## MCP

`clarity mcp` serves `check_text(text, config?)`, `score_text(text)` and `list_rules()` over STDIO. Logs go to stderr.

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

## Configuration

`clarity.yml` in this repository is the complete default pack: every category weight and cap, every rule and its allowance. Pass `--config` with a file that contains only your changes. Rules merge by `id`: an existing id overrides those fields, a new id adds a rule, `disabled: true` removes one.

```yaml
readability:
  target_grade: [8, 12]
  fail_outside_band: false

rules:
  - {id: intensifier, max_per_1k: 3}
  - {id: hedge, disabled: true}
```

### Watchlist

Add terms without writing a rule. Findings report under the `watchlist` category with the term as the rule id.

```yaml
watchlist:
  - {term: synergy, max_per_1k: 0}
  - {term: "load-bearing", max_per_1k: 0, match: phrase}
  - {term: bedrock, max_per_1k: 1, require_concrete_governor: true}
```

`require_concrete_governor` fires only on metaphorical use: it checks the governed or governing noun against the bundled Brysbaert concreteness norms and fires when the rating is below 3.0.

## Adding rules

A rule needs `id`, `category` (number or slug), `severity`, `confidence`, `max_per_1k` and `scope`. Pick a backend:

Phrase, the default. spaCy `Matcher` over lemmas (or `match: lower` for surface forms):

```yaml
rules:
  - id: no-circle-back
    category: filler
    max_per_1k: 0
    severity: warning
    confidence: exact
    clause_initial: true
    message: Say what you mean.
    phrases: [circle back, touch base]
```

A raw token `pattern:` list works in place of `phrases`.

Dependency. spaCy `DependencyMatcher` patterns under `patterns:`, with `anchor` naming the node to check and optional `concreteness_max`:

```yaml
    backend: dependency
    patterns:
      - - {RIGHT_ID: verb, RIGHT_ATTRS: {LEMMA: embark}}
        - {LEFT_ID: verb, REL_OP: ">", RIGHT_ID: obj, RIGHT_ATTRS: {DEP: pobj}}
    anchor: obj
    concreteness_max: 3.0
```

Structural. A Python function registered in `src/clarity/matchers/structural.py`, referenced by name with `backend: structural` and `function:`. Tunables go under `params:`.

## Development

```sh
make test    # pytest in the dev image
make lint    # ruff, mypy, and jscpd duplicate detection
make run ARGS="rules --category 4"
```

Categories: 1 significance, 2 discovery, 3 escalation, 4 intensifiers, 5 filler, 6 corporate, 7 structural, 8 hedges, 9 false balance, 10 false agency, 11 verbosity, 12 sentence flow, 13 watchlist.

Data: concreteness norms are Brysbaert, Warriner and Kuperman (2014). The punctuation-context model is built from the Brown corpus.
