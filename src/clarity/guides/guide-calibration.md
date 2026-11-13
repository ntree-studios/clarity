# Calibration guide

## Rates

A hit rate is matches per 1,000 words. `good_rate_per_1k` is the rate on the writing the user
approves of. `bad_rate_per_1k` is the rate on the writing they want to catch.

## Ratio

ratio = bad rate / good rate.

| ratio | reading |
|---|---|
| 3.0 or more | the rule discriminates; keep it |
| 1.5 to 3.0 | weak; the rule describes a habit both corpora share; discard under the floor |
| about 1.0 | the rule fires equally on both; it measures nothing; discard |
| under 1.0 | the rule fires more on the good writing; discard |
| infinite (good rate 0) | the rule never fires on good writing; keep, but check the sample size |

The floor is 3.0. A rule under it is rejected by `write_rules` and is never written.

## Corpus size

| per corpus | status |
|---|---|
| under 10 documents or under 5,000 words | refused: no ratio is produced |
| 10 to 24 documents or 5,000 to 19,999 words | provisional: report ratios with a provisional marker and ask for more data |
| 25 or more documents and 20,000 or more words | reliable |

## Hits and documents

A high rate from one document is one habit, not a pattern. Check `docs_hit`: a rule hitting 1 of
30 bad documents is weak evidence even at a high ratio.

## Tuning a threshold

Run `test_rule` at several values of one threshold and compare. Pick the largest value that keeps
the ratio at or above 3.0 while still catching most of the bad corpus; lowering it catches more
and raises the good-corpus rate. State the tradeoff with the numbers the tool returned.

## Limits

The ratio measures one pair of corpora. It does not prove a rule is correct on other writing.
Fixtures prove the rule's behavior on single sentences; the ratio proves it separates the two
bodies of writing. A rule needs both.
