"""One positive and one negative fixture per rule id.

The positive text must fire the rule. The negative text must not.
"""

EM = "—"

FIXTURES: dict[str, tuple[str, str]] = {
    "significance-np": (
        "The key point is that we shipped.",
        "The key opened the door.",
    ),
    "significance-phrase": (
        "The real question is whether it works.",
        "The question was whether it works.",
    ),
    "discovery-narration": (
        "Funnily enough, the build passed. It turned out the server was down.",
        "She somehow found the keys.",
    ),
    "escalation-contrast": (
        "This is not just a bug, it is a design flaw.",
        "She did not just leave the keys on the table.",
    ),
    "escalation-phrase": (
        "More than that, the build failed. And that is before you even consider the cost.",
        "I have more than that in stock.",
    ),
    "intensifier": (
        "This is genuinely useful.",
        "The deep river runs past the genuine article.",
    ),
    "filler-transition": (
        "That said, we proceed with the plan.",
        "He said that we proceed. We tracked cost in terms of dollars.",
    ),
    "corporate-flat": (
        "We leverage a robust platform.",
        "The lever moved the rock.",
    ),
    "corporate-metaphor": (
        "Let us delve into the idea of freedom.",
        "She navigated the city by bus.",
    ),
    "structural-rule-of-three": (
        "It is faster, cheaper, and more reliable.",
        "It is fast and cheap.",
    ),
    "structural-fragments": (
        "Not fast. Not cheap. Just broken.",
        "The build failed. The team fixed it.",
    ),
    "structural-question-answer": (
        "Why does the cache fail? The cache fails because of stale keys.",
        "Why does the cache fail? Keys expire early.",
    ),
    "structural-restatement": (
        "# Caching\n\nThe cache speeds up reads. It stores hot keys. "
        "The cache speeds up reads again.",
        "# Caching\n\nThe cache speeds up reads. It stores hot keys. "
        "Eviction removes stale entries.",
    ),
    "structural-rather-than": (
        "We chose speed rather than safety.",
        "She would rather leave than stay.",
    ),
    "structural-which-is": (
        "We cut scope, which is exactly the point.",
        "Which is better?",
    ),
    "em-dash": (
        f"He left {EM} quickly.",
        "He left quickly, then returned – late.",
    ),
    "sentence-length-variance": (
        "The cat sat down. The dog ran off. The bird flew by. The fish swam on. "
        "The cow ate hay. The pig dug in.",
        "The cat sat. After a long and winding afternoon the dog finally ran off toward the "
        "distant hills. Birds sing. The fish, which had waited all day for a quiet moment, "
        "swam. Cows eat. Pigs dig deep holes near the old fence every single morning.",
    ),
    "adjective-stack": (
        "A big, bold, shiny car arrived.",
        "A big car arrived.",
    ),
    "hedge": (
        "This can help to reduce cost.",
        "This reduces cost.",
    ),
    "hedge-stacking": (
        "This is arguably somewhat useful.",
        "This is arguably useful. It is somewhat slow.",
    ),
    "false-balance-while": (
        "While speed matters, it is also true that safety matters.",
        "While the kettle boiled, she read.",
    ),
    "false-balance-one-size": (
        "There is no one-size-fits-all answer.",
        "One size fits this shoe.",
    ),
    "false-balance-it-depends": (
        "# Choice\n\nPick tools carefully. It depends.",
        "# Choice\n\nIt depends on load.\n\nWe measure it.",
    ),
    "false-agency": (
        "The architecture wants a single entry point.",
        "The committee decided to wait. She knows the answer. Washington insists on it.",
    ),
    "false-agency-document-source": (
        "The report says costs rose.",
        "The report was long.",
    ),
    "false-agency-data-soft": (
        "The data suggest a clear trend.",
        "The data were clean.",
    ),
    "false-agency-data-hard": (
        "The data wants more rows.",
        "The data suggest a clear trend.",
    ),
    "long-sentence": (
        "The team shipped the build after the long review because the lead wanted every "
        "test to pass before the release went out to the customers who had been waiting "
        "for the fix since the previous quarter when the original problem first appeared.",
        "The team shipped the build after the review. The lead wanted every test to pass.",
    ),
    "nominalization": (
        "We made a determination about the implementation.",
        "The nation has a station.",
    ),
    "expletive-construction": (
        "There are many reasons for this.",
        "Many reasons exist.",
    ),
    "function-word-ratio": (
        "Database cache invalidation strategies reduce latency considerably. "
        "Throughput improves. Engineers appreciate performance.",
        "The cache stores the keys and the server reads them from it.",
    ),
    "syllables-per-word": (
        "Organizational responsibilities necessitate comprehensive documentation, particularly "
        "regarding administrative accountability mechanisms.",
        "The cat sat on the mat and ate a fish.",
    ),
    "adjective-density": (
        "The big bright red car and the quick shiny blue truck.",
        "The cache stores keys. The server reads data. A cold start costs time.",
    ),
    "intro-transition-comma": (
        "However the build failed.",
        "However hard he tried, he failed. However, the build passed.",
    ),
    "lowercase-after-terminal": (
        "It ended. then he left.",
        "It ended. Then he left. See Dr. Smith, e.g. the dentist, at 3.5 miles.",
    ),
    "run-on-missing-comma": (
        "The build failed and the team fixed it.",
        "She opened the door and walked in.",
    ),
    "comma-splice": (
        "The build failed, the team fixed it.",
        "The build failed, and the team fixed it.",
    ),
    "clause-overload": (
        "When the build failed, the lead said that the team, which had worked all night, "
        "wanted to fix it because they believed the release mattered.",
        "The build failed, so the team fixed it.",
    ),
    "rare-punctuation-context": (
        "She went to the , store.",
        "She went to the store, then home.",
    ),
}
