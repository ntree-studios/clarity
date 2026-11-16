# Sending a document

`check_text`, `score_text` and `analyze_topics` take either `text` or `document`.

- `text` is a plain string. Clarity treats it as one section of prose. It does not read
  markdown: `#` lines, list markers and code fences are checked as ordinary text.
- `document` is a section tree. Use it whenever the content has titles, lists or separate
  parts, such as a slide deck, a web page, a report or an email with headings.

## A section

Every field is optional.

| Field | Holds |
|---|---|
| `id` | Your own label. It comes back unchanged so you can match results to your content. |
| `title` | The section's heading. |
| `subtitle` | A line under the heading. |
| `text` | Prose. Separate paragraphs with a blank line. |
| `items` | A bulleted or numbered list, one string per item, without the bullet. |
| `sections` | Child sections, in reading order. |

Each title, subtitle, paragraph and item is its own unit: a missing full stop never joins it to
the next one.

## Breaking content into sections

- The whole document is the top section. Its `title` is the document title.
- Each slide, page or heading becomes a child section.
- Boxes, columns or sub-headings inside a slide or page become that section's child sections.
- Leave out page numbers, footers, legal boilerplate, tables of figures and code. They are
  not prose.

A page with three columns:

```json
{
  "title": "Spring plan",
  "sections": [
    {
      "id": "opening",
      "title": "Opening day",
      "text": "The garden opens on April 6 with twelve new beds and a shared tool shed.",
      "sections": [
        {"title": "Beds", "subtitle": "Twelve raised beds",
         "items": ["Build the frames in March", "Fill them with compost by April 1"]},
        {"title": "Water", "subtitle": "Two new taps",
         "items": ["Run the pipe from the north wall"]},
        {"title": "Tools", "subtitle": "One shed for everyone",
         "items": ["Label every shelf", "Keep a sign-out sheet by the door"]}
      ]
    }
  ]
}
```

A title on its own: `{"title": "Three teams, one shared vision"}`.

## The response

The response repeats your tree. Each section carries:

- `path`: its position, such as `"0.2"` (the third child of the first child)
- `id` and `title`, when you sent them
- `words` and `score`: its own title, subtitle, text and items
- `rollup`: the score and words of the section and every section under it, weighted by words
- `findings`: problems in the section's own fields
- `categories`: the categories with findings, and the points each one cost
- `sections`: its child sections

The top-level `score` is the root section's rollup score. Each finding gives its `field`
(`title`, `subtitle`, `text` or `items[i]`), and its `span`, `line` and `col` count from the
start of that field. Allowances apply to each section separately, so a short section cannot
borrow allowance from a long one.

The exact shapes are in `clarity://schema/document`.
