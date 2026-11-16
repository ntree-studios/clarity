# Deterministic detection of weak and AI-style prose: linter rule inventories and computational-linguistics methods (for the spaCy-based "clarity" linter)

Scope note: "clarity" already implements phrase lists for AI tics, Jaccard sentence overlap and section restatement, novelty rate, given-new ordering, referential density, pronoun-antecedent distance, Brysbaert concreteness, MTLD, sentence-length variance, paragraph-opener repetition, list parallelism and heading hierarchy. These notes focus on what goes beyond that. Research was capped at about 20 tool calls. Items marked "(not verified this session)" come from the researcher's background knowledge and should be checked before they are quoted as fact.

## 1. Linter rule inventories: which shipped rules target AI-style or weak prose?

### Takeaway
Classic linters (proselint, write-good, Hemingway, ProWritingAid) target generic weak prose: hedging, weasel words, adverbs, passives, clichés, redundancy, glue words. Since 2025 a wave of Vale and textlint packages has targeted AI tells directly. Their rules split into two kinds: near-certain "artifact" errors (chatbot phrases, placeholders, em dashes, emoji bullets, bold-label lists) and suggestion-level stylistic tics (binary contrasts such as "not X, it's Y", abstract triads, colon reveals, recap endings, inflated vocabulary). Almost all of them are regex or word-list rules. The few that go further use morphology (textlint's colon rule) or Vale `metric`/`occurrence` checks (sentence length, readability, counts per paragraph). That leaves room for clarity's DependencyMatcher and structural backends to do the same jobs more precisely.

### Cited Findings
**proselint** (amperser/proselint). Its check IDs include `hedging` ("Avoid undermining yourself with uncertainty"), `weasel_words`, `misc.metadiscourse` ("Avoid discussing the discussion"), `misc.narcissism` ("Talk about the subject, not its study"), `misc.apologizing`, `misc.pretension`, `misc.debased`, `misc.scare_quotes`, `misc.suddenly`, `cliches.misc`, `industrial_language.corporate_speak`, `industrial_language.bureaucratese`, `industrial_language.commercialese`, `industrial_language.jargon`, `redundancy.misc`, `redundancy.ras_syndrome`, `lexical_illusions` (repeated words), `oxymorons`, `uncomparables` ("very unique"), `skunked_terms`, `mixed_metaphors`, `misc.but` (paragraph starting with "But"), and `restricted.top1000` / `restricted.elementary`, which restrict vocabulary to the top-1000 or elementary-school words — [proselint README](https://github.com/amperser/proselint)

**write-good** (btford). It ships nine checks: `passive`, `illusion` (repeated word), `so` (sentence-initial "So"), `thereIs` (sentence-initial "There is/are"), `weasel`, `adverb` ("really", "very", "extremely"), `tooWordy`, `cliches`, and `eprime` (forms of "to be", off by default). The project calls itself a "naive linter". Its own README example shows the adverb rule misfiring on "read-only", and it offers a whitelist for such cases — [write-good README](https://github.com/btford/write-good)

**textlint-rule-preset-ai-writing** (textlint-ja, Japanese). Its stated philosophy is to constrain structure rather than wording ("表現を縛るのではなく、構造を縛る") — [repo](https://github.com/textlint-ja/textlint-rule-preset-ai-writing). Rules:
- `no-ai-list-formatting`: bold-label list items (`**重要**: ...`), bold label followed by a dash, and emoji bullets (✅ ❌ 💡 🔥 🚀 ⭐ 🎯 📝).
- `no-ai-hype-expressions`: three groups, namely absoluteness ("completely solves", "solves all problems"), abstract or sensory effect ("like magic", "miraculous"), and authority or prediction ("paradigm shift", "next-generation").
- `no-ai-emphasis-patterns`: bold inside sentences, bold in headings, emoji plus bold, and bold info prefixes.
- `no-ai-colon-continuation`: a colon after a predicate-final sentence followed by a code block, list, quote or table. It uses morphological analysis (kuromojin), so noun-final labels such as "使用方法:" are allowed.
- `ai-tech-writing-guideline`: redundancy, voice, clarity, consistency and structure guidance, plus a specificity check that replaces abstract words with figures (e.g. "高速な" → "50ms未満の").
- Source: [repo](https://github.com/textlint-ja/textlint-rule-preset-ai-writing); [Zenn article](https://zenn.dev/hibara428/articles/a4235e23f04110). The colon rule was split out so it could be disabled separately — [PR #17](https://github-users.yhajoa.workers.dev/textlint-ja/textlint-rule-preset-ai-writing/pull/17)

**jdkato/voices** (from Vale's author). The always-on core flags inflated words, binary contrasts, throat-clearing, puffery, weasel attribution, colon reveals, recap endings and weak verbs. Its word lists come from Peter Yang's `no-ai-slop` (MIT). Optional voices:
- "Direct": no hedging, no preamble, sentences under 25 words, paragraph reading ease above 50.
- "Simple": the 850 words of Basic English and reading ease above 80.
- "Human": no "Great question" openers, no "hope this helps" closers, one dash per paragraph.
- "Claude": no "genuinely", no emoji, no bullets in a refusal, at most two headers, three bold spans and fifteen sentences.
- Source: [jdkato/voices](https://github.com/jdkato/voices); [Vale blog: Voices](https://vale.sh/blog/voices). The blog argues that a rule costs nothing until a draft breaks it, while a prompt instruction is paid for on every request — [Vale blog](https://vale.sh/blog/voices)

**krishnasunkam/vale-ai-tells** (17 rules).
- Error level: `Dash` (em and en dashes, including numeric ranges), `CodeToken` (ALL_CAPS_UNDERSCORE identifiers), `FilePath`, `StatusBracket`, `SectionCode`, `NeverTag` (antithesis ending in "never").
- Suggestion level: `EpigramContrast`, `NegParallel`, `CopulaInflation` (presumably "serves as" or "stands as" in place of "is"), `HiddenVerb` (nominalization), `Passive`, `Cliche`, `WeakResume`, `VirtueHonest`, `LinkText`, `AbstractTriad`, `Adverb`.
- Source: [EveryDev listing](https://www.everydev.ai/tools/vale-ai-tells/llms.txt). Only six of the rules are described there, so the descriptions of the rest are inferred from their names.

**ammil-industries/vale-signs-of-ai-writing**. Claude generated it from Wikipedia's "Signs of AI writing" page, and humans reviewed it.
- Error: chatbot phrases, technical glitches, placeholders, tracking URLs (e.g. `utm_source=chatgpt.com`).
- Warning: hedging clusters, knowledge-cutoff references, enumeration style.
- Suggestion: vocabulary, transitions, passive voice, symbolic language. The author describes these as "suspicious but common in human writing".
- The author notes Vale cannot flag stray Markdown outside Markdown contexts without flagging all Markdown.
- Source: [ammil.industries article](https://hn.jakechampion.name/reader/https://ammil.industries/signs-of-ai-writing-a-vale-ruleset)

**JMill/deslop**: a Vale package for stock phrases, hedges and structural tics, with CI workflows — [tomevault listing](https://tomevault.io/tome/JMill/deslop). **petergyang/no-ai-slop**: a Python tool that removes 20+ AI-slop patterns — [ossinsight](https://ossinsight.io/analyze/petergyang/no-ai-slop). The npm package **slopless** also exists — [socket.dev](https://socket.dev/npm/package/slopless/overview/0.2.31). None of these three repos was opened, so their rule lists are unverified.

**Wikipedia "Signs of AI writing"** (WikiProject AI Cleanup). This advice page is the upstream source for several of the rulesets above. Its categories include inflated importance ("a pivotal moment"), promotional tone, rule-of-three phrasing, overblown symbolism, repetitive transitions and editorial commentary. It is descriptive, and it warns that no single sign proves AI authorship. Coverage puts it at about 15,000 words — [TechCrunch, Nov 2025](https://techcrunch.com/2025/11/20/the-best-guide-to-spotting-ai-writing-comes-from-wikipedia/); [page mirror](https://markdown.new/https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)

**ProWritingAid Sticky Sentences.**
- Glue index = percentage of glue words in the document. The target for published writing is 40%.
- A sentence is "sticky" above 60% glue words and "semi-sticky" at 40–60%.
- Sticky is computed only for sentences longer than 8 words, semi-sticky only for sentences longer than 15.
- Some third-party reviews cite 45% instead, which conflicts with the official help page.
- Source: [ProWritingAid help](https://help.prowritingaid.com/article/50-how-to-use-the-sticky-sentences-report); [third-party: Medium on 25 reports](https://medium.com/personal-growth/what-are-the-25-writing-reports-in-this-editing-tool-anyway-e569fd0e167d)

**Empirically derived vocabulary lists.**
- Kobak et al. (Science Advances 2025) found about 900 "excess words" in 15M+ PubMed abstracts (2010–2024), e.g. "delves", "showcasing", "underscores", "potential", "findings", "crucial", "pivotal".
- Excess vocabulary in 2024 was mostly style words, whereas COVID-era excess was topical.
- They estimate at least 13.5% of 2024 abstracts were LLM-processed, up to 40% in some subcorpora. Version 4 of the preprint said 10% and 30%.
- The list is public — [arXiv 2406.07016](https://arxiv.org/abs/2406.07016v5); [berenslab/llm-excess-vocab](https://github.com/berenslab/llm-excess-vocab)

**Antislop** (Paech et al., arXiv Oct 2025; listed at ICLR 2026).
- Builds per-model "slop fingerprints" of over-represented words and n-grams relative to human baselines (Reddit creative writing, Project Gutenberg).
- Some patterns appear more than 1,000× as often in LLM output as in human text.
- Fingerprints cluster within model families.
- Code (MIT): github.com/sam-paech/auto-antislop.
- Source: [arXiv 2510.15061](https://arxiv.org/abs/2510.15061); [mlanthology ICLR 2026](https://mlanthology.org/iclr/2026/paech2026iclr-antislop/)

### Inferences
- **Coverage map against clarity.** The phrase-list backend already covers most lexical tics. The new rule *types* in 2025–26 AI-slop packages are mostly structural:
  - (i) binary contrast or negative parallelism ("It's not X, it's Y"; "not just X but Y"; "X, not Y"). In spaCy: a DependencyMatcher on `neg` + copula + contrasting conjunct, or a Matcher across a sentence boundary.
  - (ii) Abstract triads: three coordinated nouns, two or more of them abstract (low Brysbaert concreteness, or suffixes -tion/-ity/-ness/-ment). Use `conj` chains in the dependency parse plus the concreteness norms clarity already has.
  - (iii) Colon reveal: a short clause, then ":", then a short payoff. A structural function over tokens.
  - (iv) Recap endings: the final paragraph starts with "In summary/Ultimately/Overall", or its lemma overlap with earlier text is high. clarity's section-restatement Jaccard can be scoped to the last paragraph.
  - (v) Copula inflation: lemmas "serve/stand/act" + "as" in place of "be".
  - (vi) Bold-label lists and emoji bullets. Markdown AST structural checks.
  - (vii) Dash density per paragraph. jdkato's "Human" voice allows at most one per paragraph.
  - (viii) Present-participial tails such as ", highlighting/underscoring/reflecting...". This matches Reinhart's 5× finding in section 6: a Matcher for a comma followed by a VBG whose head is the root verb (`advcl`).
- **Severity tiers are a useful pattern.** The rulesets agree on a three-tier severity scheme: artifact (error), likely tic (warning), common-in-human (suggestion). clarity could adopt it.
- **Implementability.** All rules listed in this section are easy in spaCy. A dependency-based version of the regex rules should cut false positives. Example: NegParallel by regex fires on "not only ... but also", which is legitimate in human prose.

### Gaps
- I did not fetch the Vale Microsoft, Google, write-good, proselint or Readability packages, LanguageTool's style-rule list, alex, Hemingway docs or Grammarly docs.
- Background knowledge (not verified this session):
  - Hemingway highlights "hard to read" and "very hard to read" sentences by readability grade, adverbs, passive voice, and phrases with simpler alternatives.
  - Vale's Readability package implements Flesch-Kincaid, Gunning Fog, SMOG, Coleman-Liau and LIX as `metric` rules.
  - Microsoft and Google styles include Wordiness, Adverbs, Passive, Contractions, FirstPerson, Will and Ellipses.
  - ProWritingAid also has Glue/Pacing (slow paragraphs = long introspective passages), Echoes (a repeated word within a window), Transitions (percentage of sentences with transitions, target about 25%) and Overused Words reports.
  - Grammarly's clarity checks (wordy sentences, intensifiers, hard-to-read sentences) are proprietary and undocumented.
- The full rule files for vale-ai-tells, deslop and voices were not opened. Exact regexes and the five vale-ai-tells rules that are not described remain unverified.
- I found no published false-positive rates for any AI-slop linter.

## 2. Topic drift and paragraph unity

### Takeaway
The classical deterministic tools are TextTiling-style lexical cohesion curves, lexical chains, the entity grid and Centering transitions. All of them reduce to tracking repeated content lemmas or entities (subjects and objects) across sentences, so they are implementable with spaCy alone. The entity grid is the best validated of them. Lexical chains need WordNet. At paragraph scale (5–10 sentences), raw lexical-overlap signals are noisy and should be used as relative or outlier signals, not absolute cut-offs.

### Cited Findings
- **TextTiling (Hearst 1997).**
  - Text is split into pseudosentences of w tokens. Adjacent blocks of k pseudosentences are compared by cosine similarity of term frequencies, and the resulting curve is smoothed.
  - Depth score at gap i = lpeak + rpeak − 2·g, where lpeak and rpeak are the highest scores reached scanning outward from the gap while the curve keeps rising.
  - Boundary cutoff:
    - "HC" (the NLTK default) = mean(depth) − sd/2
    - "LC" = mean(depth) − sd
  - Candidates within 4 gaps of a stronger candidate are removed.
  - NLTK defaults: w=20, k=10, smoothing width 2, one smoothing round, English stopword list.
  - Sources: [NLTK texttiling source](https://www.nltk.org/_modules/nltk/tokenize/texttiling.html); [Hearst 1997, Computational Linguistics](https://aclanthology.org/J97-1003/)
- **Lexical chains.** Morris & Hirst (1991) built chains of related words with Roget's Thesaurus as a cohesion and structure signal — [ACL J91-1002](https://aclanthology.org/J91-1002/). Barzilay & Elhadad (1997) built WordNet-based chains for summarization — [ACL W97-0703](https://aclanthology.org/W97-0703/).
- **Entity grid (Barzilay & Lapata 2008).**
  - Builds a sentences × entities matrix whose cells hold the entity's grammatical role (S subject / O object / X other / – absent).
  - Coherence features are the probabilities of role transitions (e.g. S→S, S→–, –→S) over sentence pairs.
  - A ranking model is trained on original vs. permuted documents.
  - Source: [ACL J08-1001](https://aclanthology.org/J08-1001/). The extended version adds entity-specific features — [Elsner & Charniak 2011](https://aclanthology.org/P11-2022/).
- **Centering Theory** defines transitions between utterances (Continue, Retain, Smooth Shift, Rough Shift) from the backward-looking center (Cb) and the preferred center (Cp, the highest-ranked entity, usually the subject) — [Grosz, Joshi & Weinstein 1995](https://aclanthology.org/J95-2003/).
- **Coh-Metrix referential cohesion** tracks noun overlap, argument overlap, stem overlap and content-word overlap between local sentences. It also has LSA overlap between sentences and paragraphs — [GSU Coh-Metrix overview](https://sites.gsu.edu/csal/readibillity/coh-metrix-advanced-overview); [McNamara et al. 2014, Cambridge](https://www.cambridge.org/core/books/abs/automated-evaluation-of-text-and-discourse-with-cohmetrix/cohmetrix-measures/0C1D5CBBF51C5BBF2AE2478534305341)

### Inferences
- **Paragraph unity score (easy).** Compute content-lemma (NOUN/PROPN/VERB/ADJ) overlap of each sentence with the paragraph's first sentence and with the paragraph centroid. Flag sentences whose overlap with both is zero and that share no entity with the previous sentence. This is a local "off-topic sentence" detector.
  - Use per-document z-scores (e.g. flag below mean − 1 sd, as TextTiling's LC policy does) rather than fixed thresholds, because overlap scales with sentence length and genre.
- **Heading–body overlap (easy).** Compute the fraction of a heading's content lemmas that appear in its section's first paragraph, or anywhere in the section. Zero overlap suggests a generic heading or a drifted section.
- **Intra-section drift (easy).** Run TextTiling inside a section, with k reduced to about 3–4 sentences because sections are short. If a boundary falls *inside* a paragraph, or a single section contains a strong boundary, the section may cover two topics.
- **Simplified entity grid (moderate).** Entities are noun-chunk head lemmas plus PROPN spans. Roles come from `dep_`: nsubj/nsubjpass → S, dobj/pobj-of-verb → O, else X.
  - Per paragraph, compute the share of adjacent-sentence pairs with no shared entity (–→– transitions everywhere). Also compute the share of "salient" entities, i.e. entities that occur in two or more sentences.
  - AI text often has *high* local overlap, so a low-cohesion flag catches drift, not slop. The paired signal for slop is very high entity repetition with low novelty, which clarity's novelty-rate metric already covers.
  - Coreference is not in core spaCy (it needs coreferee or an experimental component). Without it, pronoun subjects should map to the previous sentence's subject heuristically.
- **Centering transitions (moderate).** Use subject continuity as Cp. Count "rough shifts", where the subject entity changes and is absent from the previous sentence. A paragraph with a rough shift on most sentence pairs is a candidate for a "jumpy paragraph" warning.
- **Lexical chains (needs extra data).** WordNet via NLTK, or word vectors (`en_core_web_md`/`lg`) as a substitute for synonym and hypernym links. Lower priority given how much plain lemma overlap already captures.

### Gaps
- Reported accuracies were not re-verified this session. From background knowledge (not verified this session), Barzilay & Lapata report sentence-ordering discrimination accuracy of roughly 85–90% on news corpora (Earthquakes, Accidents) for the entity grid with coreference and salience, and Hearst reports TextTiling boundary precision and recall in the 0.6–0.7 range against human judges.
- Background knowledge (not verified this session): Miltsakaki & Kukich (2004) found the proportion of Rough-Shift transitions predicts lower essay scores. No URL was retrieved.
- I found no published thresholds for paragraph-level "first sentence vs. rest" overlap. All thresholds proposed above are inferences.

## 3. Specificity and genericity

### Takeaway
Li & Nenkova's Speciteller shows that cheap surface and dictionary features predict sentence specificity reasonably well: about 73.6% supervised accuracy against a 54.6% baseline, and 81.6% after co-training. Every feature it uses can be reproduced with spaCy plus small lexicons. A key finding: general sentences have *higher* familiarity and imageability, and concreteness separated the classes only weakly. Brysbaert concreteness alone is therefore an incomplete specificity signal.

### Cited Findings
- **Speciteller features** (Li & Nenkova, AAAI 2015), 14 shallow features:
  - Surface: number of words; numbers per word; capital letters per word; non-alphanumeric symbols per word; average word length; stopword proportion (570-word list); count of 100 explicit discourse connectives.
  - Dictionary: General Inquirer polar words; MPQA strongly subjective words; MRC familiarity mean; MRC imageability mean; min/max/mean IDF.
  - Results (logistic regression, 885 test sentences, majority baseline 54.58%): surface features 71.53%, word properties 72.43%, combined 73.56%. After co-training with word representations: 81.58% accuracy (F 79.45), against the 77.40% Louis & Nenkova (2011) baseline.
  - Specific sentences are longer. General sentences are more subjective and have higher familiarity and imageability. Concreteness showed only small differences and was dropped.
  - Sources: [paper text](https://object.cloud.sdsc.edu/v1/AUTH_da4962d3368042ac8337e2dfdd3e7bf3/ml-papers-txt/AAAI/2015/fast_and_accurate_prediction_of_sentence_specificity__7fcfce8a.txt); [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/9517); [code, CC BY-NC-SA](https://github.com/jjessyli/speciteller)
- Ko, Durrett & Li (AAAI 2019) extended specificity prediction to real-valued scores and to non-news domains (Twitter, reviews, conversation) — [arXiv 1811.05085](https://arxiv.org/pdf/1811.05085)
- The textlint AI-writing guideline rule explicitly flags abstract performance adjectives and recommends quantified replacements ("fast" → "under 50 ms") — [textlint-ja repo](https://github.com/textlint-ja/textlint-rule-preset-ai-writing)

### Inferences
- **Specificity score per sentence or paragraph (easy).**
  - Inputs: numerals (`like_num`, NUM), named entities (`doc.ents`, especially DATE, CARDINAL, PERCENT, MONEY, QUANTITY, ORG, PRODUCT, GPE), PROPN ratio, IDF (needs a frequency list, e.g. `wordfreq` Zipf scores as the inverse), average word length, stopword proportion, and a subjectivity/evaluative lexicon (MPQA is freely available).
  - Use: flag paragraphs with zero numbers or entities *and* a high rate of evaluative adjectives as "generic claims". Restrict this to expository or technical modes to avoid flagging narrative or opinion prose.
- **Vague quantifier and claim matcher (easy).** Flag "significant(ly)", "various", "numerous", "a range of", "many", "improved", "enhanced", "better performance" when no number or entity appears in the same sentence. This is a composite rule: phrase list + absence check.
- **WordNet hypernym depth (needs extra data: NLTK WordNet).** Take the mean minimum depth of noun synsets, where deeper means more specific. I found no validation study in this session, and sense ambiguity makes it noisy. An alternative is a corpus frequency rank via `wordfreq`, which approximates generality cheaply and loosely tracks Speciteller's IDF features.
- Because Li & Nenkova found general sentences have *higher* imageability and familiarity, a familiarity proxy (word frequency) may separate generic from specific sentences better than concreteness does.

### Gaps
- No URL was retrieved for validation of WordNet hypernym depth as a specificity measure.
- MRC familiarity and imageability norms are older and smaller than Brysbaert's. Glasgow norms are a modern alternative for imageability (not verified this session).

## 4. Information density and redundancy

### Takeaway
Propositional idea density (CPIDR) is a well-validated deterministic POS-rule metric. Compression ratio and n-gram repetition are cheap document-level redundancy signals, but no prose-linting thresholds have been published for them. Over-represented n-gram fingerprints (Antislop) are the empirical way to grow AI-tic lists.

### Cited Findings
- **CPIDR** (Brown, Snodgrass, Kemper, Herman & Covington 2008).
  - Method: POS-tag the text (Penn tags), count verbs, adjectives, adverbs, prepositions and conjunctions as propositions, then apply readjustment rules. CPIDR 3.2 has about 37 rules; for example, a linking verb plus a predicate adjective counts as one proposition ("seems old").
  - Idea density = propositions ÷ words.
  - Reported agreement with human consensus was higher than inter-human agreement. A secondary source cites 97% inter-rater agreement, but this was not checked against the original tables.
  - CPIDR 5.1 reports 95% confidence intervals.
  - Sources: [Brown et al. 2008 PDF](https://www.ai.uga.edu/sites/default/files/inline-files/caspr/BrownSnodgrassKemperHermanCovington2008.pdf); [CPIDR 5 manual](https://www.ai.uga.edu/sites/default/files/inline-files/caspr/CPIDR-5-Manual.pdf)
- **Antislop over-representation.** The ratio of a word's or n-gram's frequency in model output to its frequency in human corpora identifies "slop". After the authors' FTPO fine-tuning, the mean over-representation of the top-40 words reportedly fell by 73% (secondary review) — [arXiv 2510.15061](https://arxiv.org/abs/2510.15061)
- **Kobak's excess-word method.** Compare observed word frequency in a year with a counterfactual extrapolated from previous years. Excess words are those with a large frequency ratio or gap — [arXiv 2406.07016](https://arxiv.org/abs/2406.07016v5)

### Inferences
- **Idea density (easy).** spaCy gives Penn tags in `tag_`, so the CPIDR rules port directly. Low density (e.g. below about 0.40 propositions per word) suggests filler. However, the norms come from spoken and elderly-writing studies, not expository prose, so the threshold must be calibrated on clarity's own corpus.
- **Compression ratio (easy, no spaCy needed).** Compute `len(zlib.compress(text)) / len(text)` per section, or the conditional increment `C(prev+para) − C(prev)` per paragraph. The increment works as a "new information" measure that complements novelty rate. Short texts compress poorly regardless, so normalize by length or compare against a shuffled baseline. No published linter thresholds were found.
- **Repeated n-grams (easy).** Count content-lemma 3- and 4-grams that occur two or more times across a document, excluding named-entity spans and terms defined in headings. Flag phrases repeated in three or more paragraphs as "echo" phrases. This generalizes ProWritingAid's Echoes report.
- **Nominalization density (easy).** Suffix list (-tion, -ment, -ness, -ity, -ance, -ence) on NOUN tokens that have a verb or adjective root. This ties to Reinhart's 2× finding in section 6 and to vale-ai-tells' HiddenVerb rule.

### Gaps
- I found no published thresholds for compression ratio as a prose-redundancy lint, and no validation of n-gram repetition counts against human quality judgments.
- The CPIDR rule list (all 37 rules) was not extracted. It is in the 2008 PDF and the manuals linked above.

## 5. Coh-Metrix indices that are deterministic

### Takeaway
Most Coh-Metrix cohesion indices are pure counting over lemmas and POS tags and can be reproduced in spaCy: referential overlap (noun, argument, stem, content-word; adjacent vs. all-pairs), connective incidence by type, lexical diversity, syntactic indices, and situation-model particles such as causal verbs vs. causal connectives. LSA indices can be replaced by word-vector cosine or by TF-IDF cosine.

### Cited Findings
- **Index families** in Coh-Metrix: Descriptive, Text Easability principal components (word concreteness, syntactic simplicity, verb cohesion, and others), Referential Cohesion (noun, argument and content-word overlap), LSA, Lexical Diversity, Connectives (causal, logical, temporal), Situation Model, Syntactic Complexity, Syntactic Pattern Density, Word Information, Readability — [GSU Coh-Metrix overview](https://sites.gsu.edu/csal/readibillity/coh-metrix-advanced-overview)
- Coh-Metrix tracks four types of lexical co-reference: common noun overlap, pronoun overlap, argument overlap and stem overlap. Causal cohesion is the ratio of causal connectives (particles) to causal verbs — [Cambridge book chapter listing](https://www.cambridge.org/core/books/abs/automated-evaluation-of-text-and-discourse-with-cohmetrix/cohmetrix-measures/0C1D5CBBF51C5BBF2AE2478534305341); [PMC table](https://pmc.ncbi.nlm.nih.gov/articles/PMC8100971/table/T2)
- Coh-Metrix 3.0 includes only a subset of the hundreds of indices the team explored — [Cambridge](https://www.cambridge.org/core/books/automated-evaluation-of-text-and-discourse-with-cohmetrix/AE4A1D5DCCBA1AE3A9632E9D4D380270/listing?pageNum=2)

### Inferences
- **Not yet in clarity, all easy:**
  - (a) Argument overlap: shared noun lemma *or* a pronoun matching a noun in the previous sentence, adjacent and global. Report it as a binary per sentence pair, the way Coh-Metrix does.
  - (b) Stem overlap: a noun in sentence n shares a stem with any content word in n−1. This catches derivational links such as "decide" → "decision".
  - (c) Connective incidence per 1,000 words by type: additive, adversative, causal, temporal, logical.
    - Over-use of additive connectives ("Moreover", "Additionally", "Furthermore") at sentence start is a known AI tic. Under-use of causal connectives in argumentative sections suggests listing without reasoning.
  - (d) Causal ratio: causal connectives ÷ causal verbs.
  - (e) Verb cohesion: repeated verb lemmas across sentences.
  - (f) LSA given/new and adjacent-paragraph similarity, replaced by spaCy vector cosine (needs a `md`/`lg` model) or by TF-IDF cosine (easy).
- **Calibration.** Coh-Metrix publishes grade-level norms, not thresholds, so any flags should be relative (z-scores) or calibrated on a reference corpus.

### Gaps
- The exact 3.0 index codes (e.g. CRFNO1, CRFAO1, CRFSO1, CRFCWO1, CNCAll, CNCCaus, CNCADC, CNCTemp, SMCAUSr) are from background knowledge (not verified this session). The cohmetrix.com documentation page returned empty content.
- Validity: from background knowledge (not verified this session), Coh-Metrix cohesion indices correlate only weakly with human essay-quality scores (McNamara, Crossley & McCarthy 2010). Higher-rated essays did *not* show more cohesion. That cautions against "more overlap = better".

## 6. Deterministic, interpretable AI-text signals (not model perplexity)

### Takeaway
The strongest peer-reviewed interpretable evidence is Reinhart et al. (PNAS 2025). Using Biber's register features, instruction-tuned LLMs over-use present participial clauses (up to 5.3× the human rate), nominalizations (about 2×), "that" clauses as subject (2.6×) and phrasal coordination (1.9×), and GPT-4o under-uses agentless passives (about 0.5×). Random forests on these features separate human text from a single LLM at 93–98%, but generalization across models and genres is weak. Lexical over-representation (Kobak, Antislop) is the other robust family. Every Biber feature is spaCy-implementable.

### Cited Findings
- **Reinhart et al.** (arXiv 2410.16107; PNAS 122(8), Feb 2025). Parallel corpora of human text and text from Llama 3 variants and GPT-4o were scored with Biber's feature set.
  - Present participial clauses: up to 5.3× the human rate for GPT-4o (d=1.38); 2–5× for instruction-tuned Llama.
  - "That" clauses as subject: 2.6× (d=0.77).
  - Nominalizations: 2.1× (d=1.23); 1.5–2× for Llama-Instruct.
  - Phrasal coordination: 1.9× (d=0.81).
  - Downtoners: GPT-4o uses more than humans; Llama uses fewer.
  - Agentless passive: GPT-4o about 0.5× the human rate.
  - Clausal coordination: GPT-4o avoids it; Llama over-uses it.
  - Base models are closer to human rates than instruction-tuned models.
  - Classification: seven-way random forest 66% (chance about 14%); human vs. one LLM 93–98%.
  - Caveats: accuracy dropped substantially on M4 arXiv abstracts (GPT-3.5). The authors disclaim use as a detector or a tool for policing student writing.
  - Sources: [arXiv HTML v2](https://arxiv.org/html/2410.16107v2); [NJIT record](https://researchwith.njit.edu/en/publications/do-llms-write-like-humans-variation-in-grammatical-and-rhetorical/)
- **Kobak et al.** In 2024 the excess vocabulary was style words (verbs and adjectives), not content words, which makes it a deterministic lexical signal — [arXiv 2406.07016](https://arxiv.org/abs/2406.07016v5)
- **Antislop.** Slop fingerprints are model-family specific and cluster within families. A fixed list therefore goes stale as models change and should be versioned and refreshed — [arXiv 2510.15061](https://arxiv.org/abs/2510.15061)

### Inferences
- **High-value new rules or metrics from Biber features (all easy in spaCy):**
  - Present participial clause rate: a VBG heading an `advcl`, or sentence-final ", VBG ..." (e.g. ", highlighting the importance of"), per 1,000 words.
  - Nominalization rate.
  - Phrasal coordination rate: `cc` + `conj` between same-POS nouns, adjectives or verbs, not clauses. This also feeds triad detection.
  - Subject "that"-clause rate: `csubj` with a "that" marker.
  - Downtoner and amplifier lists.
  - Agentless passive rate: `nsubjpass`/`auxpass` with no `agent` child. Under-use is a signal, which inverts the classic "avoid passive" rule. clarity could report it as a metric rather than a lint.
  - Report each as a document metric with a "human reference range". Reinhart's ratios suggest flagging at about 2× a reference-corpus rate for participial clauses and nominalizations.
- **Other interpretable signals (easy, but sourced here only through the linter packages above):**
  - Em-dash density (vale-ai-tells Dash rule; jdkato's one dash per paragraph).
  - Colon density.
  - Bold and emoji density in Markdown.
  - Sentence-initial additive connectives.
  - Burstiness, i.e. coefficient of variation of sentence length. clarity already has sentence-length variance.
  - Function-word profiles and POS n-gram profiles are standard stylometry but need a reference corpus and are better as metrics than as lints.
- **False-positive risk.** Reinhart's per-feature effects are population-level (d ≈ 0.8–1.4). Per-document flags on short texts will misfire, so use them as aggregate metrics with explanations, not as accusations of AI authorship.

### Gaps
- No peer-reviewed source for deterministic burstiness or punctuation-distribution detectors was retrieved this session. GPTZero-style "burstiness" is popularly described but usually computed with model perplexity, not sentence length.
- I did not obtain a survey of interpretable-feature AI-text detection with cross-domain error rates. Reinhart's own cross-dataset drop is the only quantified generalization caveat found.
- Biber feature definitions (Biber 1988, 67 features) were not fetched. Implementation would follow the Multidimensional Analysis Tagger or the `pybiber` spaCy-based package. Both are from background knowledge (not verified this session).
