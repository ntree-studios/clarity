# Composition schema

Composition fields read findings and metrics, so a detector can be a few lines of YAML. All of
them resolve at load. An unknown rule, metric or category, a disabled member, a composite referring to
another composite, or a bad operator fails with the rule id and the field.

## Composite rules

A rule with `backend: composite` fires in a scope when other rules' findings share it. One
compound tell is one finding. The member findings come back as `children` and are no longer
reported on their own.

```yaml
rules:
  - id: hedged-intensifier
    category: composite
    backend: composite
    count_scope: sentence
    max_per_scope: 0
    severity: error
    confidence: exact
    requires_all:
      - rule: hedge
      - rule: intensifier
    note: hedging and intensifying in one sentence cancel each other out
```

`requires_all` needs every member, `requires_any` needs at least one, `requires_none` needs none
present. A composite needs `requires_all` or `requires_any`. Each member is `{rule, min_count}`
with `min_count` defaulting to 1. Composites evaluate after every atomic rule and every metric,
once, and cannot name other composites.

## active_when

Applies a rule only when a metric condition holds. A condition is `{metric, op, value}` with `op`
one of `lt`, `lte`, `gt`, `gte`, `eq`. Give `key` to test a different scalar of the metric.

```yaml
rules:
  - id: long-sentence
    active_when: {metric: sentence_length_variance, op: lt, value: 5.0}
```

## allowance_when

Replaces the allowance when a condition holds. The first entry that holds wins. An entry names a
metric condition or `over_allowance: <category>` (another category), plus the allowance field
that matches the rule's `count_scope`.

```yaml
rules:
  - id: passive-agentless
    allowance_when:
      - {metric: mean_concreteness, op: gt, value: 3.5, max_per_1k: 4}
  - id: escalation-phrase
    allowance_when:
      - {over_allowance: corporate-vocabulary, max_per_1k: 0}
```

## suppress_if

A match that any condition covers is not a finding and uses no allowance. Conditions:

- `near: {pos | lemma | ent | pattern, within: N}` tests tokens within N tokens of the match.
  `pattern` is a regex over the nearby text.
- `in_scope: {count_scope, rule}` holds when another rule has a match in the same scope.
- a metric condition `{metric, op, value}`.

```yaml
rules:
  - id: weasel-attribution
    suppress_if:
      - near: {pos: PROPN, within: 10}
      - near: {pattern: "\\[\\d+\\]", within: 15}
```

`clarity explain <rule> "text"` shows the condition that suppressed a match and shows each
composite member's state in every scope it evaluated.
