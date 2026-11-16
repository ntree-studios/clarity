# Using clarity well

Read this before calling `check_text` for someone else's writing.

## Send the right shape

- Prose with no headings or lists: send `text`.
- Anything with headings or bullets, such as a slide deck: send `document`, a section tree. See
  `clarity://guide/document`.
- Leave out code and quoted material the writer did not write. Drop tables of figures, page
  numbers and footers as well. Clarity checks every word it gets as the writer's own prose.

## Pick a profile

| Writing | Profile |
|---|---|
| Documentation, API guides, READMEs, how-to steps | `technical` |
| Email, memos, proposals, reports, slide decks for a business reader | `business` |
| Essays, articles, opinion pieces, blog posts | `essay` |
| Anything else, or when unsure | none (the default rules only) |

A project can define its own profiles in `.clarity/profiles/`. `clarity://profiles` lists the
ones available.

## Switch off rules that do not fit

`check_text`, `score_text` and `analyze_topics` take two optional lists:

- `disable`: rule ids or category ids to switch off.
- `enable`: rule ids or category ids to switch on, including rules the shipped pack leaves off,
  such as `ease-words`.

A category id stands for every rule in that category. When a name is both a rule id and a
category id, clarity reads it as the category. Both lists apply after the config files and the
profile, so they win over both. Disables go first, so `disable: [structural-tics]` with
`enable: [em-dash]` leaves only `em-dash` on in that category. Switching off a rule also
switches off any composite rule built on it. An unknown id is an error, and the message
includes the id.

`clarity://rules` lists the active rules with their category, message, description and
remediation, and
`clarity://categories` lists the categories. On the command line the same switches are
`--disable` and `--enable`, repeated or comma separated.

| Situation | Disable |
|---|---|
| Legal or regulatory text, where passive voice and defined terms are required | `passive-agentless`, `nominalization`, `self-repetition` |
| Code comments and docstrings that quote example phrases | the rules whose examples are quoted |
| Fiction and dialogue | the categories `sentence-flow`, `hedges` and `intensifiers` |
| Translated text | `rare-punctuation-context` |

Rules that judge whole sentences already skip titles, subtitles and items, so a deck needs no
extra switches for its bullets.

## Read the findings

- Each finding has a `message` that states the pattern and a `remediation`: the change to make.
  `clarity://rules/{rule_id}` gives the rule's full description.
- `confidence: exact` means the match is the pattern named. `inferred` means the match is likely
  and worth a look.
- One weak finding on a line can be noise. Several findings on the same title, sentence or
  paragraph usually mean the line is the problem: rewrite the line instead of patching each
  finding.
- Findings with `over_allowance: false` do not lower the score. Fix them only if the line
  reads badly.
- Section scores show where the trouble is. Rewrite the lowest section first.

## When to leave a finding alone

- The phrase is a quotation, a product name or a fixed legal term.
- The writer's style guide requires it.
- Changing it would make the sentence less accurate.

Tell the writer why you left it. A user can accept a finding for good with `accept_finding` and
its id; the first six characters are enough.

## Check your own rewrite

Run `check_text` again on the rewritten text. If the rewrite swaps one tic for another, such as
replacing "not X, but Y" with "the key is Y", rewrite it again.
