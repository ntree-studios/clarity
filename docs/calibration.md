# Calibration on the human and AI corpora

Run on 2026-11-14 against `/Users/jim/clarity-corpora` (see its README for sources, models and
caveats). Every folder was measured in full: 250 documents per side for most genres, 252 for
business and 87 for technical. No document raised an error.

## Corpus state at the time of the run

- `student-essays` is the replaced set: human essays from the Argument Annotated Essays corpus,
  AI essays from GEDE. It was measured last, after the replacement.
- `encyclopedic` was re-measured on 2026-11-15 after its human side was replaced with the last
  revision of each article on or before 2019-12-31 (250 articles, 75,256 words; AI side 102,374
  words). The encyclopedic column below is from that run. The human side now has paragraphs and
  `##` headings (190 of 250 articles) and the AI side is still one flattened paragraph, so
  paragraph and section rules are biased on encyclopedic. No verdict changed: every scored rule
  still passes there (participial-tail 0.01 vs 3.99, ai-lexicon-gpt4o 0.08 vs 1.25,
  copula-inflation 0.12 vs 0.83), and `wandering-paragraph` (78 human documents, 6 AI) and
  `section-heading-mismatch` (3 human, 0 AI) fire more on people only because the AI side has no
  paragraphs or headings. The student-essays folder was re-measured in the same run and gave the
  same rates as before.
- `scientific`, `news`, `opinion-blog`, `creative` and `encyclopedic` have no paragraph breaks on
  either side. `technical` has none on the human side only, so paragraph-based rules are biased on
  technical and their technical rows are not used for a verdict.

## Rule for scoring

A rule is scored when, on at least one genre:

1. its AI rate is at least 3.0 times its human rate, and
2. it fired in at least 10 AI documents (so a ratio is not built on two hits), and
3. the genre is not a known formatting asymmetry for that rule (paragraph rules on technical).

It stays experimental if, on any genre, it fired in 5 or more human documents and the human rate
was higher than the AI rate. That rule is stricter than "3.0 on one corpus": a rule that fires
more on people in some genres would cost those writers score.

## Results per rule

Rate per 1,000 words, human / AI. A dot means no hits on either side.

| rule | business | creative | encyclopedic | news | opinion-blog | scientific | student-essays | technical |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `abstract-physical-verb` | . | . | . | . | . | 0.00 / 0.01 | . | . |
| `abstract-physical-verb-catalogued` | 0.02 / 0.05 | 0.02 / 0.03 | 0.03 / 0.01 | 0.03 / 0.02 | 0.01 / 0.09 | 0.01 / 0.05 | 0.01 / 0.03 | 0.00 / 0.07 |
| `abstract-physical-verb-observed` | . | 0.01 / 0.02 | 0.00 / 0.01 | 0.00 / 0.02 | 0.00 / 0.02 | 0.02 / 0.03 | . | 0.00 / 0.02 |
| `ai-lexicon-2026` | 0.00 / 0.07 | 0.18 / 0.57 | 0.00 / 0.06 | 0.03 / 0.48 | 0.07 / 0.48 | 0.09 / 0.32 | 0.05 / 1.27 | 0.04 / 0.13 |
| `ai-lexicon-gpt4` | 0.02 / 0.41 | 0.06 / 0.02 | 0.09 / 6.40 | 0.19 / 0.23 | 0.06 / 0.05 | 0.09 / 0.48 | 0.20 / 1.76 | 0.04 / 0.18 |
| `ai-lexicon-gpt4o` | 0.14 / 0.61 | 0.03 / 0.01 | 0.08 / 1.25 | 0.11 / 0.58 | 0.03 / 0.07 | 0.50 / 1.60 | 0.25 / 6.20 | 0.04 / 0.26 |
| `ai-lexicon-gpt5` | . | . | . | . | . | 0.00 / 0.01 | . | . |
| `assistant-leakage` | 0.00 / 0.05 | 0.01 / 0.00 | . | . | . | . | . | . |
| `comparison-no-verdict` | . | . | 0.01 / 0.00 | . | . | 0.02 / 0.00 | 0.04 / 0.03 | . |
| `copula-inflation` | . | 0.01 / 0.02 | 0.12 / 0.83 | 0.02 / 0.06 | 0.00 / 0.01 | 0.04 / 0.05 | 0.04 / 0.63 | 0.00 / 0.09 |
| `engagement-bait` | . | . | . | . | 0.00 / 0.02 | . | 0.00 / 0.10 | . |
| `focus-gap-section` | . | . | . | . | . | . | . | . |
| `generic-paragraph` | 0.00 / 0.19 | . | . | . | . | 0.00 / 0.01 | 0.09 / 2.24 | 0.00 / 0.02 |
| `off-topic-share` | . | . | . | . | . | . | . | . |
| `orphan-paragraph` | . | . | . | . | . | . | . | . |
| `participial-tail` | 0.02 / 0.49 | 0.01 / 0.02 | 0.01 / 3.99 | 0.05 / 0.16 | 0.01 / 0.04 | 0.11 / 0.38 | 0.00 / 1.53 | 0.04 / 0.33 |
| `recap-closer` | . | . | . | . | . | 0.00 / 0.10 | 0.10 / 0.47 | . |
| `salience-frame` | . | . | . | . | 0.01 / 0.00 | . | . | . |
| `section-heading-mismatch` | . | . | 0.09 / 0.00 | . | . | . | . | . |
| `source-disclaimer` | 0.00 / 0.02 | . | . | . | . | . | . | . |
| `stiff-synonym` | 0.11 / 0.39 | 0.06 / 0.02 | 0.19 / 1.10 | 0.07 / 0.02 | 0.06 / 0.02 | 0.39 / 0.50 | 0.21 / 0.58 | 0.00 / 0.20 |
| `template-placeholder` | . | . | . | . | . | . | . | . |
| `topic-digression` | . | . | . | . | . | . | . | 0.00 / 0.04 |
| `topic-drift` | . | . | . | . | . | . | . | 0.00 / 0.04 |
| `unquantified-claim` | 0.47 / 1.24 | 0.05 / 0.04 | 0.21 / 1.68 | 0.13 / 0.12 | 0.07 / 0.10 | 0.44 / 0.69 | 0.53 / 2.16 | 0.08 / 0.53 |
| `wandering-paragraph` | 0.77 / 1.00 | 0.21 / 0.19 | 1.29 / 0.06 | 0.04 / 0.07 | 0.10 / 0.16 | 0.01 / 0.00 | 1.43 / 2.95 | 0.16 / 1.51 |

## Verdicts

| rule | passes on (ratio) | fires more on people (human docs hit) | verdict |
| --- | --- | --- | --- |
| `abstract-physical-verb` | none | none | experimental |
| `abstract-physical-verb-catalogued` | opinion-blog 10.5x | none | scored |
| `abstract-physical-verb-observed` | none | none | experimental |
| `ai-lexicon-2026` | creative 3.1x, news 14.7x, opinion-blog 7.3x, scientific 3.4x, student-essays 25.7x | none | scored |
| `ai-lexicon-gpt4` | business 18.3x, encyclopedic 68.8x, scientific 5.2x, student-essays 8.9x | creative 0.3x (7), opinion-blog 0.8x (7) | experimental |
| `ai-lexicon-gpt4o` | business 4.5x, encyclopedic 15.7x, news 5.4x, scientific 3.2x, student-essays 25.1x, technical 6.5x | none | scored |
| `ai-lexicon-gpt5` | none | none | experimental |
| `assistant-leakage` | none | none | experimental |
| `comparison-no-verdict` | none | none | experimental |
| `copula-inflation` | encyclopedic 6.9x, student-essays 17.1x | none | scored |
| `engagement-bait` | none | none | experimental |
| `focus-gap-section` | none | none | experimental |
| `generic-paragraph` | student-essays 25.9x | none | scored |
| `off-topic-share` | none | none | experimental |
| `orphan-paragraph` | none | none | experimental |
| `participial-tail` | business 21.5x, encyclopedic 299.9x, news 3.3x, scientific 3.5x, student-essays (no human hits), technical 8.2x | none | scored |
| `recap-closer` | scientific (no human hits), student-essays 4.7x | none | scored |
| `salience-frame` | none | none | experimental |
| `section-heading-mismatch` | none | none | experimental |
| `source-disclaimer` | none | none | experimental |
| `stiff-synonym` | business 3.4x, encyclopedic 5.9x | creative 0.3x (7), news 0.3x (9) | experimental |
| `template-placeholder` | none | none | experimental |
| `topic-digression` | none | none | experimental |
| `topic-drift` | none | none | experimental |
| `unquantified-claim` | encyclopedic 7.9x, student-essays 4.1x | creative 0.8x (6), news 0.9x (14) | experimental |
| `wandering-paragraph` | none (technical 9.4x is a formatting artifact) | creative 0.9x (26) | experimental |

Seven rules are scored: `abstract-physical-verb-catalogued`, `ai-lexicon-2026`,
`ai-lexicon-gpt4o`, `copula-inflation`, `generic-paragraph`, `participial-tail` and
`recap-closer`. The rest stay experimental: they are reported and never scored.

Rules that never fired here are not shown to be useless. `assistant-leakage` and
`template-placeholder` catch chat leftovers, and none of these corpora contain unedited chat output.

## Section headings on real articles

`section-heading-mismatch` fired 7 times in 3 of the 190 Wikipedia articles with headings. Five
were functional headings, which name a role and not a subject: Plot, Overview, Synthesis,
Reactions, Applications. The rule now skips a list of such headings (`heading not_in [...]` in
the rule's YAML). The two that remain, "Rolling stock" and "Conductivity and magnetism", are
topical headings whose body uses other words (trains and cars; electrons and spin). TF-IDF cannot
see that, so the rule stays experimental.

Topic analysis reached 3 of the 250 Wikipedia articles: the median article has 4 chunks at the
default `chunk.min_words` 25.

## Topic settings

The sweep changed one setting at a time from the defaults, on the full technical folders and on
the first 100 student essays per side. "Analyzed" is the number of documents whose topic report
had status `ok`; "topic hits" counts findings of the six graph-based topic rules
(`wandering-paragraph` is paragraph-based and is left out).

| corpus | setting | analyzed | median chunks | topic hits |
| --- | --- | --- | --- | --- |
| technical AI | defaults (min_count 10) | 10/87 | 5 | 4 |
| technical AI | min_count 5 | 59/87 | 5 | 5 |
| technical AI | min_words 15 | 11/87 | 6 | 5 |
| technical AI | min_words 15, min_count 5 | 62/87 | 6 | 9 |
| technical AI | min_words 40 | 8/87 | 5 | 2 |
| technical AI | k 4 (min_count 5) | 59/87 | 5 | 16 |
| technical AI | k 8 (min_count 5) | 59/87 | 5 | 1 |
| technical AI | min_modularity 0.1 (min_count 5) | 59/87 | 5 | 26 |
| technical AI | min_modularity 0.3 (min_count 5) | 59/87 | 5 | 1 |
| technical AI | window 1 (min_count 5) | 59/87 | 5 | 9 |
| technical AI | window 5 (min_count 5) | 59/87 | 5 | 4 |
| technical human | every setting | 0/87 | 1 | 0 |
| student essays, AI | defaults | 0/100 | 5 | 0 |
| student essays, AI | min_count 5 (any other setting) | 72/100 to 73/100 | 5 | 2 |
| student essays, human | defaults | 0/100 | 5 | 0 |
| student essays, human | min_count 5 (any other setting) | 52/100 to 58/100 | 5 | 0 |

Findings:

- With `chunk.min_count: 10` the topic analysis runs on almost no real document in these corpora.
  Essays and emails have a median of 5 or 6 paragraph chunks, and the flattened genres have one.
  Only 10 of 87 technical AI answers reach 10 chunks.
- The topic rules therefore have too few hits on any corpus to compute a ratio. They stay
  experimental, and their thresholds (`align.on_topic_min` 0.5, the 0.75 and 0.6 anchor
  thresholds, the 0.75 weighted-degree threshold, the 0.3 heading threshold) stay as set on the
  planted set (`tests/planted_topics.py`). They are not calibrated.
- Lowering `communities.min_modularity` or `graph.k` makes the topic rules fire more; raising
  them makes them fire less. Without a human side that reaches the analysis, there is no evidence
  to prefer any value, so the proof of concept's values are kept.

Chosen topic defaults: unchanged. `chunk.min_words` 25, `chunk.min_count` 10, `graph.k` 6,
`communities.min_modularity` 0.2, `smoothing.window` 3.

What would settle them: paired human and AI documents of 10 or more paragraphs (long-form
articles, reports or documentation with paragraph breaks on both sides).

## Starter profiles

Style score on each profile's genre, human and AI, with the profile and with `--profile none`.

| profile | genre | side | docs | p10 | median | p90 |
| --- | --- | --- | --- | --- | --- | --- |
| technical | technical | human | 87 | 67.9 | 81.8 | 93.2 |
| technical | technical | ai | 87 | 47.9 | 72 | 86.5 |
| none | technical | human | 87 | 68.5 | 83 | 93.2 |
| none | technical | ai | 87 | 50.9 | 72.2 | 86.7 |
| business | business | human | 252 | 77.7 | 88.25 | 95.1 |
| business | business | ai | 252 | 82.8 | 90 | 95 |
| none | business | human | 252 | 79.7 | 89.55 | 95.8 |
| none | business | ai | 252 | 83.5 | 90.85 | 95.5 |
| essay | student-essays | human | 250 | 72.5 | 82.3 | 90.7 |
| essay | student-essays | ai | 250 | 66.9 | 76.6 | 85.7 |
| none | student-essays | human | 250 | 72.5 | 82.3 | 90.7 |
| none | student-essays | ai | 250 | 66.9 | 76.6 | 85.7 |

The AI median is below the human median on technical (72 vs 81.8 with the profile) and student
essays (76.6 vs 82.3). On business the AI median is higher (90 vs 88.25): the business AI side is
polished rewrites and short answers, which these rules do not separate, and the human emails carry
habits (passives, long sentences) the business profile tightens. The essay profile gives the same
scores as no profile here because `generic-paragraph`, the rule it used to switch on, is now
scored in the pack, and `comparison-no-verdict` almost never fires on these essays.

## Claude-written text (2026-11-15)

Opus, Sonnet and Haiku (run as Claude Code subagents) each wrote the same 28 pieces from
ordinary requests, with no mention of style or testing: 6 essays and 6 finance answers on the
human corpora's own prompts, 5 work emails, 5 programming answers, 3 encyclopedia articles and
3 blog or opinion posts (28,238 words, in `/Users/jim/clarity-corpora/ai-claude/`).

Median score with no profile, human folder vs Opus / Sonnet / Haiku:

| genre | human | Opus | Sonnet | Haiku |
| --- | --- | --- | --- | --- |
| essays | 82.3 | 84.0 | 84.2 | 81.8 |
| finance answers | 89.7 | 83.3 | 89.2 | 90.7 |
| emails | 91.5 | 81.4 | 84.7 | 87.5 |
| programming answers | 83.0 | 87.9 | 85.7 | 88.5 |
| articles | 82.4 | 75.5 | 87.0 | 97.6 |
| blog and opinion | 76.0 | 81.4 | 84.3 | 80.2 |

The pack does not separate this text from human writing. None of the seven rules scored above
fired once on it, and it contains no em-dash. The rules that fire more on Claude than on people
are `rule-of-three` (about 2x), `wandering-paragraph` and `template-placeholder` (the emails
end in `[Your name]`, which the requests left open). The weak-writing rules (long sentences,
passives, noun stacks, run-ons) fire less on Claude than on people, which lifts its scores.

Candidate patterns, counted by regular expression only (per 1,000 words, Claude vs human
folders): a trailing negation such as "…, not Y." or "isn't X, it's Y" 0.50 vs 0.03 to 0.12;
"what matters" 0.17 vs 0.00 to 0.01. The sample is too small to score either (about 14 and 5
hits).

## trailing-negation and what-matters (2026-11-15)

Measured on every human and AI folder plus the Claude set, which grew to 270 documents and
101,609 words (Opus 88, Sonnet 94, Haiku 88; requests in `ai-claude/requests*.tsv`). The Claude
pieces are compared with the human folder of their genre: essays with `student-essays`, finance
answers and emails with `business`, programming answers with `technical`, articles with
`encyclopedic`, blog and opinion posts with `opinion-blog`.

Rate per 1,000 words (documents hit):

| genre | `trailing-negation` human / other AI / Claude | `what-matters` human / other AI / Claude |
| --- | --- | --- |
| business | 0.09 (4) / 0.05 (2) / 0.75 (20) | 0.00 / 0.00 / 0.17 (6) |
| creative | 0.13 (13) / 0.27 (31) / - | 0.02 (2) / 0.01 (1) / - |
| encyclopedic | 0.04 (3) / 0.06 (6) / 0.11 (1) | 0.00 / 0.00 / 0.00 |
| news | 0.12 (14) / 0.55 (55) / - | 0.02 (2) / 0.09 (11) / - |
| opinion-blog | 0.13 (15) / 0.88 (70) / 0.60 (8) | 0.02 (2) / 0.05 (7) / 0.20 (3) |
| scientific | 0.03 (4) / 0.03 (4) / - | 0.00 / 0.00 / - |
| student-essays | 0.09 (7) / 0.16 (12) / 0.65 (13) | 0.00 / 0.03 (2) / 0.22 (5) |
| technical | 0.24 (5) / 0.68 (25) / 0.48 (6) | 0.00 / 0.00 / 0.16 (2) |

Claude overall: `trailing-negation` 0.60 per 1,000 words in 48 of 270 documents; `what-matters`
0.17 in 16 of 270.

`trailing-negation` first fired more on people in business (5 documents) and scientific text
(10). Most of those were concessions, not reframes: "is not enough, but synchrotron tomography
can…", "is not completely understood, but are…". The "not X but Y" pattern now skips a degree
word after "not" and a new clause after "but", which removed them. The ", not Y." corrections
people write ("…not the main server.") still count; Claude writes them several times as often.

Verdicts: both scored. `trailing-negation` passes on business (Claude 8.2x), student essays
(Claude 7.5x), news (other AI 4.4x) and opinion-blog (other AI 6.7x). `what-matters` passes on
news (other AI 5.7x); it fired on 16 Claude documents and on at most 2 human documents per genre.
Neither fires more on people in any genre. `salience-frame` lost its "what matters" phrases to
`what-matters`.

Effect on the score: 57 of the 270 Claude documents lose points, 1.9 on average, and the Claude
median moves from 84.5 to 83.75. These two rules alone do not make Claude score below people.

## Slide-deck rules (2026-11-16)

A client slide deck (kept outside the repository) showed slop that the rules missed. Task 16
widened three rules, changed one and added two title rules. Rates are per 1,000 words; "docs" is
the number of documents with a hit. Scripts and output: `run-2026-11-15/t16/`.

| rule | change | where it separates people from AI |
| --- | --- | --- |
| `trailing-negation` | adds ", not X, so …", "VERB, never VERB", "VERB instead of VERB-ing" | opinion 0.15 vs 0.95 (6.5x, 73 AI docs); news 0.12 vs 0.57 (4.6x, 57) |
| `what-matters` | matches every form of "matter" ("the months that matter most") | news 0.02 vs 0.09 (5.7x, 11 AI docs) |
| `abstract-physical-verb-catalogued` | adds "turns X into", "opens … dollars", "holds … down", "earns the next" | opinion 0.02 vs 0.14 (8.6x, 17 AI docs) |
| `rule-of-three` | fires only when one block (paragraph, title or item) holds two or more lists of three; plain noun lists such as "region, month, and team" are skipped | student essays 0.21 vs 1.33 (6.2x, 51 AI docs); opinion 1.42 vs 4.67 (3.3x, 171 AI docs) |

The old `rule-of-three` (any single list of three) was about 2x on these corpora. People were
never higher than AI on the density version. Human business text (1.26 vs 3.09) and technical
text (0.48 vs 0.79) stay under 3x.

`stock-title-shape` (a short label, a colon and a claim; "N things, one thing"; ", and what…";
", each one …-ing") and `weak-title` (two or more of stock-title-shape, noun-stacking and an
out-of-band function-word ratio in one title) read titles and subtitles only. On the 735 headings
of the pre-2020 Wikipedia articles, neither fired once. The corpora have no headings written by
an AI (the AI files carry the prompt's title), so no ratio can be computed. Both are scored on
the zero false-alarm rate, an exception to the 3.0x rule above, made because the deck needed
them; collect AI-written headings to test them properly.

On the deck's missed lines, 10 of 11 now fire. The miss is "so finance analyzes instead of
assembling": spaCy tags "analyzes" as a plural noun, so no word pattern can match it.

## Proposal, not implemented: relative anchor alignment

The absorbing-walk anchor alignment is compressed into a narrow, high band. On the planted set,
on-topic chunks sat at 0.85 to 0.94 and off-topic chunks at 0.48 to 0.84, depending on the
subject. A fixed threshold therefore fits one document and not the next: the sourdough drift was
missed because its mortgage paragraphs shared the word "home" with the title and scored 0.84.

The proposal is to rank instead of threshold: compare each chunk's anchor alignment with the
document's own main-topic chunks (for example, its distance below their median, or its rank among
all chunks), and test that in rules. It would be a new record field computed from the existing
walk, with no change to the proof of concept's method. It was not implemented because the method
is fixed until the user decides.

## Reproducing

The scripts are in `/Users/jim/clarity-corpora/_scripts/calibration/` (the 2026-11-15 re-run and its output in `run-2026-11-15/`): `measure_full.py` (per-rule hits and documents per
folder), `policy.py` (the verdicts), `sweep.py` (topic settings) and `profile_scores.py`. Each
runs inside the dev image with the corpora mounted read-only at `/corpora`. `clarity test
--corpus <genre>/human --against <genre>/ai` gives the same per-rule rates for one genre.

## Re-measure after the plain-text change (2026-11-16)

The rates above were mostly measured when clarity stripped markdown. The corpora contain markdown
that clarity now reads as plain text. This run used the existing `measure.py` and `policy.py` from
`_scripts/calibration/` on the seven scored rules plus `count-noun-fragment`, over all eight
genres (250 documents per side, 252 for business, 87 for technical). No document raised an error.

Rate per 1,000 words, human / AI. A dot means no hits on either side.

| rule | business | creative | encyclopedic | news | opinion-blog | scientific | student-essays | technical |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `abstract-physical-verb-catalogued` | 0.02 / 0.05 | 0.02 / 0.04 | 0.03 / 0.02 | 0.03 / 0.06 | 0.02 / 0.14 | 0.01 / 0.05 | 0.01 / 0.02 | 0.00 / 0.07 |
| `ai-lexicon-2026` | 0.00 / 0.07 | 0.18 / 0.57 | 0.00 / 0.06 | 0.03 / 0.48 | 0.07 / 0.48 | 0.09 / 0.32 | 0.05 / 1.15 | 0.04 / 0.11 |
| `ai-lexicon-gpt4o` | 0.13 / 0.59 | 0.03 / 0.01 | 0.08 / 1.24 | 0.11 / 0.58 | 0.03 / 0.07 | 0.50 / 1.60 | 0.24 / 5.64 | 0.04 / 0.22 |
| `copula-inflation` | . | 0.01 / 0.02 | 0.12 / 0.82 | 0.02 / 0.06 | 0.00 / 0.01 | 0.04 / 0.05 | 0.03 / 0.58 | 0.00 / 0.07 |
| `count-noun-fragment` | 0.02 / 0.00 | . | . | 0.07 / 0.06 | 0.02 / 0.01 | . | . | 0.04 / 0.00 |
| `generic-paragraph` | 0.00 / 0.19 | . | . | . | . | 0.00 / 0.01 | 0.08 / 2.06 | 0.00 / 0.02 |
| `participial-tail` | 0.02 / 0.47 | 0.01 / 0.02 | 0.01 / 3.95 | 0.05 / 0.16 | 0.01 / 0.04 | 0.11 / 0.38 | 0.00 / 1.39 | 0.04 / 0.26 |
| `recap-closer` | . | . | . | . | . | 0.00 / 0.10 | 0.09 / 0.42 | . |

`policy.py` gives the same verdict as the table above for every rule:

| rule | passes on (ratio) | verdict |
| --- | --- | --- |
| `abstract-physical-verb-catalogued` | opinion-blog 8.6x | scored |
| `ai-lexicon-2026` | creative 3.1x, news 14.7x, opinion-blog 7.3x, scientific 3.4x, student-essays 25.6x | scored |
| `ai-lexicon-gpt4o` | business 4.5x, encyclopedic 15.9x, news 5.4x, scientific 3.2x, student-essays 23.9x, technical 5.5x | scored |
| `copula-inflation` | encyclopedic 7.0x, student-essays 17.1x | scored |
| `count-noun-fragment` | none | experimental |
| `generic-paragraph` | student-essays 26.1x | scored |
| `participial-tail` | business 21.5x, encyclopedic 303.7x, news 3.3x, scientific 3.5x, student-essays (no human hits), technical 6.4x | scored |
| `recap-closer` | scientific (no human hits), student-essays 4.7x | scored |

No verdict would change. The ratios moved a little (`abstract-physical-verb-catalogued` on
opinion-blog went from 10.5x to 8.6x, and `ai-lexicon-gpt4o` on technical from 6.5x to 5.5x), and
every scored rule still passes on at least one genre with no genre where people trip it more.
`count-noun-fragment` fires at least as often on people as on AI in business, news, opinion-blog
and technical, and no genre reaches 3.0x, so it stays experimental. Verdicts in the table above were not edited.
