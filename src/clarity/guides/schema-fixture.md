# Fixture schema

Fixtures live in `*.test.yml` files next to the rule files (`rules/` in a config directory). One
YAML document per rule, separated by `---`. The file name without `.test.yml` is the group name.

```yaml
rule: framing-noun-phrase
should_fire:
  - "The honest framing is that most advice isn't a rule."
  - text: "The simple answer is no."
    expect: {count: 1, span: "The simple answer"}
should_not_fire:
  - "The honest broker in the deal was the escrow agent."
  - "A simple answer helps nobody."
```

A case is a string, or an object with `text` and optional `expect` (`count`: exact number of
matches, `span`: a matched span, compared with whitespace collapsed and case folded).

## Minimum

At least 1 `should_fire` and 2 `should_not_fire` per rule. Negative cases matter more than
positive ones: they prove the rule leaves ordinary prose alone.

## Good negative cases

1. A near miss that differs from a positive by one token.
2. A legitimate use of the same vocabulary.
3. A real hit from the good corpus that the writer confirms is acceptable.

## Good positive cases

Take them from real hits in the bad corpus (`find_matches`), not from invented sentences.

A multi-paragraph case is one string with `\n\n` between paragraphs. A section case needs a
markdown heading line.
