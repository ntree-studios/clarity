# Genre conventions: business, scientific, and technical writing (plus brief news/legal) for clarity profiles

Scope note: general paragraph technique and general plain-language guides are covered by another researcher. This file covers only how genre changes the advice. Marking convention used throughout:
- **[guide]** = style-guide or authority opinion (prescriptive)
- **[corpus]** = corpus or empirical frequency data (descriptive)
- **[unverified]** = source located but exact wording/number not confirmed against the primary text in this session; the report writer should treat it as provisional.

Source-quality caveat: several primary texts (Longman Grammar, HBR Guide, Minto, AR 25-50, Nature formatting guide) could not be fetched directly (paywall, login redirect, or no online text). Where a number comes only through a secondary page, it is flagged.

Existing clarity profiles (read from `src/clarity/profiles/*.yml` in this repo, all self-described as "Starting point, not authority"): academic = passive-agentless max 8/1k, nominalization max 12/1k, weasel-attribution 0; technical = construction x1.5, corporate-vocabulary x0.5, verbosity x1.2, readability weight 0, disables section-restatement and long-sentence, subject-verb-distance max 12 tokens; marketing = corporate-vocabulary 0, escalation 0, hedges x2.0, grade 7-10; fiction = readability weight 0, disables long-sentence, passive-agentless, fragment-triad, sentence-length-variance. There is no business profile yet.

## Business writing conventions (BLUF, Minto, memos, email, Amazon narratives, SEC, voice, length, bullets)

### Takeaway
Business-writing authorities agree on answer-first structure, active voice, personal pronouns ("you"/"we"), short sentences (about 15 to 20 words on average), and concrete data in place of adjectives. They disagree on bullets: the SEC handbook says to use bullet lists "wherever possible", while Amazon's six-page narratives deliberately use prose instead of slides and bullets. A business profile therefore needs a memo/narrative variant and a brief/email variant, or else it should leave bullets alone.

### Cited Findings
**Answer-first / BLUF / pyramid**
- BLUF (bottom line up front) comes from US military writing. Guidance teaching it says to put "the recommendation, conclusion, or reason for writing in the first or second paragraph, not at the end" [guide]. — [JMU handout, Writing in the Army Style](https://www.jmu.edu/uwc/tutor-resources/MSL202L15%20Writing%20in%20the%20Army%20Style.pdf); background at [Wikipedia: BLUF](https://en.wikipedia.org/wiki/BLUF_(communication))
- The governing regulation is AR 25-50 (DTIC copy dated 5 March 2001, superseding the 1988 edition). Secondary sources give its sentence target inconsistently: "average about 15 words", "15 or fewer", or "15 to 20" (the last one is from a Serbian defence guide, not AR 25-50). They also give paragraph limits ("no more than one inch deep"; "6 to 7 sentences") that rest on weak sources [guide, unverified]. — [DTIC AR 25-50 copy](https://apps.dtic.mil/sti/pdfs/ADA402203.pdf); [JMU handout](https://www.jmu.edu/uwc/tutor-resources/MSL202L15%20Writing%20in%20the%20Army%20Style.pdf); [Serbian MoD defence writing style](https://www.smesta.mod.gov.rs/formats_of_military_correspondence/defence_writing_style.56.html)
- Army writing guidance names the active voice as "the major style change" that makes Army writing clear and says Army writers overuse the passive [guide]. — [Army Writing Style (Scribd copy)](https://www.scribd.com/document/35903830/Army-Writing-Style)
- Microsoft's top-10 style tips: "Get to the point fast. Lead with what's most important. Front-load keywords for scanning. Make customer choices and next steps obvious." [guide] — [Microsoft Writing Style Guide, Top 10 tips](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)
- Minto's Pyramid Principle (governing thought first, then grouped supporting arguments, each group summarizing the ideas below it) is the consulting standard. I could not fetch the primary text this session [guide, unverified]. See Gaps.

**Amazon narrative memos**
- Primary source: Bezos's 2017 shareholder letter describes "narratively structured six-page memos" written in place of slides. It says authors "mistakenly believe a high-standards, six-page memo can be written in one or two days or even a few hours", and that "The great memos are written and re-written, shared with colleagues who are asked to improve the work... They simply can't be done in a day or two." [guide] — [Amazon 2017 Letter to Shareholders](https://www.aboutamazon.com/news/company-news/2017-letter-to-shareholders)
- Secondary reports of Amazon's internal writing rules all repeat "replace adjectives with data" and "no weasel words". Examples: "Customers love Prime" rewritten as a concrete spending/retention figure; "most" replaced with "87%"; "significantly" and "nearly" flagged when no metric is given. The popular "six rules" list (sentences under 30 words, adjectives to data, the "so what?" test) traces to social-media threads, not to an Amazon document [guide, unverified]. — [Trevor Lasn, Amazon's No Weasel Words Rule](https://www.trevorlasn.com/blog/amazons-no-weasel-words-rule); [swipefile: Amazon's internal writing advice](https://swipefile.com/amazons-internal-writing-advice); [Network Capital, The Amazon Way of Writing](https://networkcapital.substack.com/p/the-amazon-way-of-writing)

**SEC Plain English Handbook (1998), the most detailed official business-disclosure guide**
- Its list of the most common problems: "Long sentences; Passive voice; Weak verbs; Superfluous words; Legal and financial jargon; Numerous defined terms; Abstract words; Unnecessary details; Unreadable design and layout" [guide]. — [SEC, A Plain English Handbook (1998), p.17](https://www.sec.gov/pdf/handbook.pdf)
- On passive voice: "Don't ban the passive voice, use it sparingly... Use the passive voice only when you have a very good reason for doing so. When in doubt, choose the active voice." It singles out "passive with agent deleted" as common in disclosure documents [guide]. — [SEC handbook](https://www.sec.gov/pdf/handbook.pdf)
- On hidden verbs: look for "to be", "to have" or another weak verb with "a noun derived from a verb that usually ends in -tion. Find the noun and try to make it the main verb" [guide]. — [SEC handbook](https://www.sec.gov/pdf/handbook.pdf)
- On personal pronouns: "No matter how sophisticated your audience is, if you use personal pronouns the clarity of your writing will dramatically improve." It recommends "first-person plural (we, us, our/ours) and second-person singular (you, your/yours)" [guide]. — [SEC handbook](https://www.sec.gov/pdf/handbook.pdf)
- It also says "Ruthlessly eliminate jargon and legalese"; "Use bullets to list information wherever possible"; and the SEC Rule 421(d) plain-English elements include "Short sentences", "Definite, concrete, everyday words", "Active voice", "Tabular presentation or bullet lists for complex material", and "No multiple negatives" [guide/regulatory]. — [SEC handbook](https://www.sec.gov/pdf/handbook.pdf)

**Sentence length targets**
- Garner (LawProse) recommends an average sentence length of 20 words and says not every sentence needs to be 20. Secondary summaries attribute "20 or fewer words" to his HBR Guide to Better Business Writing [guide; HBR attribution unverified]. — [LawProse Lesson #269](https://lawprose.org/lawprose-lesson-269-average-sentence-length/); [UT Austin legal writing blog: sentence length](https://sites.utexas.edu/legalwriting/2021/05/01/sentence-length/); [Shortform summary of HBR Guide](https://www.shortform.com/summary/hbr-guide-to-better-business-writing-summary-bryan-a-garner)
- Army style: average of about 15 words (inconsistently reported; see above).
- Amazon (secondary): under 30 words per sentence [unverified].

**Voice, address, word choice (corporate/product writing)**
- Microsoft: "Shorter is always better"; "Write like you speak... Avoid jargon"; "Use contractions like it's, you'll, you're, we're, and let's"; "Prune every excess word"; "start each statement with a verb. Edit out you can when it isn't necessary. Avoid weak phrasing like there is, there are, and there were"; use sentence-style capitalization; use the serial comma [guide]. — [Microsoft Writing Style Guide, Top 10 tips](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)

### Inferences
- Business writing is the genre where weasel attribution and unquantified intensifiers ("significantly", "most", "many customers") hurt most, because Amazon-style practice and SEC disclosure rules both treat a missing number as a defect. A business profile should tighten weasel and intensifier rules, not relax them.
- Bullets: the SEC (disclosure: scannability) and Amazon (narrative memos: reasoning must be in connected prose) disagree outright. The genre split is decision memo/narrative (prose required; a high bullet density counts as slop) versus email, brief or disclosure (bullets encouraged). A linter should not penalize bullets in a generic business profile. It could offer a `business-narrative` variant that flags bullet-heavy sections.
- Answer-first is checkable in a weak, heuristic form: the first paragraph (or the first two sentences of an email) should contain a recommendation, request or conclusion marker (modal "should/recommend/propose/request/need", a decision verb, or a date/number deadline). Openings that only give context ("As you know...", "I wanted to reach out...", "In today's fast-paced...") are flaggable.
- Passive voice and nominalizations should keep general-prose strictness or be stricter in business: the SEC explicitly targets agentless passive and -tion nominalizations.

### Gaps
- Minto Pyramid Principle primary text, the HBR Guide (Garner) text, and HBR articles on writing were not fetched. Exact wording and any numeric targets in them are unverified.
- No corpus frequency data was found for passives, hedges or nominalizations in real business memos or email (Biber-style register numbers for business correspondence exist in the literature but were not retrieved).
- The Economist Style Guide and McKinsey internal norms were not retrieved. Any banned-word lists from them are unverified.
- No authoritative paragraph-length number for business writing was found. The "one inch" and "6-7 sentences" Army figures rest on weak sources.
- Numbers and dates formatting for business (e.g. numerals for 10 and above, ISO dates) was not sourced this session, beyond Google's general "Use unambiguous date formatting" (see Technical).

## Scientific writing conventions (IMRaD, voice and first person, hedging, tense, nominalization, citation)

### Takeaway
Major journals and style guides now prefer active voice and accept "we". Corpus data, though, show that published academic prose is still the most passive-heavy register (about 25% of finite verbs are passive, against about 2% in conversation). It is also heavily hedged: about 15 to 21 hedges per 1,000 words overall and about 36 per 1,000 in Discussion sections, with very few in Methods. Profiles should therefore relax passive voice and hedging by section, not across the whole document. The scientific failure mode for AI text is excess "AI vocabulary" (e.g. "delves" ~28x its expected frequency in 2024 PubMed abstracts), not hedging as such.

### Cited Findings
**Passive vs active voice: guides**
- Nature: "Nature journals prefer authors to write in the active voice" (quoted by secondary sources; the official formatting-guide page redirects to a login and could not be fetched). A Nature editor's blog says the active-voice preference is long-standing, "enshrined in the style manual", and recommended to all authors at acceptance. Passive-voice papers appear in Nature only at the author's request [guide]. — [Editage quoting Nature guidelines](https://www.editage.com/insights/how-to-effectively-use-active-and-passive-voice-in-research-writing); [Nature blog: Active is better than passive](https://blogs.nature.com/blog/active_is_better_than_passive/); [Nature Masterclasses](https://masterclasses.nature.com/writing-for-greater-impact/50732650)
- Sheldrake reports surveying 55 physical and biological science journals: only two required passive constructions, and some, including Nature, positively encouraged active voice [secondary survey, informal]. — [Sheldrake, The Active Voice in Science](https://rupertsheldrake.substack.com/p/the-active-voice-in-science)
- Disagreement: Methods sections are still widely described as traditionally passive. CASRAI notes passive "remains the traditional choice for Methods" though some journals now accept or prefer active. Editage says Nature and Science papers use passive extensively in Methods [guide/observational]. — [CASRAI dictionary: active vs passive voice](https://casrai.org/dictionary/term/active-voice-vs-passive-voice); [Editage](https://www.editage.com/insights/how-to-effectively-use-active-and-passive-voice-in-research-writing)
- APA 7 (sections 4.13 and 4.16) favours active voice, allows passive when the actor is unimportant, and allows first person ("I" for sole authors, "we" only for co-authors) in place of the "the authors" third person. The APA page did not render in this session [guide, unverified]. — [APA Style: active and passive voice](https://apastyle.apa.org/style-grammar-guidelines/grammar/active-passive-voice); [APA Style: first-person pronouns](https://apastyle.apa.org/style-grammar-guidelines/grammar/first-person-pronouns)

**Passive voice: corpus**
- Longman Grammar of Spoken and Written English (Biber et al. 1999; ~40M-word corpus of conversation, fiction, news and academic prose, normed per million words): passives are "most common in academic prose, where they account for about 25 per cent of all finite verbs". News is about 15% and conversation about 2% [corpus; the 25% comes from the Longman Student Grammar text, the 15%/2% from an OCR-garbled scan, so check the book]. — [Longman Student Grammar (vdoc copy)](https://vdoc.pub/documents/longman-student-grammar-of-spoken-and-written-english-4gkoo039ija0); [LGSWE (epdf copy)](https://epdf.pub/longman-grammar-of-spoken-and-written-english.html); [TESL-EJ review of LGSWE (corpus design)](https://tesl-ej.org/ej15/r14.html)
- LGSWE: the present perfect passive occurs over 1,000 times per million words in academic prose and news [corpus]. — [LGSWE (epdf copy)](https://epdf.pub/longman-grammar-of-spoken-and-written-english.html)
- Biber (2012) also shows passives far more common in academic writing than in conversation (the table could not be read cleanly) [corpus]. — [Biber 2012, Corpus Linguistics and Linguistic Theory](https://jan.ucc.nau.edu/biber/Biber/Biber_2012.pdf)

**Hedging: legitimate epistemic marking (Hyland)**
- Hyland (1995), "The Author in the Text: Hedging Scientific Writing", corpus of 26 cell and molecular biology research articles (71,635 words): "hedging represents more than one word in every 50". Total of 1,474 hedging devices, which is 20.6 per 1,000 words [corpus]. — [Hyland 1995, ERIC ED390258](https://files.eric.ed.gov/fulltext/ED390258.pdf)
- Same study, by section: "82% of all items occur in the Results and Discussion sections with only 4% in methods. In RAs with an IMRD organisation, Discussions averaged 36 devices per thousand words with Introductions and Results yielding 20 each." Methods has "one tenth of the density of epistemic items found in Discussion sections" (≈3.6/1k) [corpus]. — [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf)
- Same study, by device per 1,000 words: lexical verbs 4.9, adverbial constructions 4.4, adjectives 3.9, modal verbs 3.5. The verbs indicate, suggest, appear and propose make up 55.7% of lexical-verb hedges. Would, may and could make up 76.6% of epistemic modals. "43% of hedges occurring in the same sentence as at least one other device" (hedges cluster) [corpus]. — [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf)
- Hyland's rationale: hedges mark claims as "provisional, pending acceptance by one's peers" and reflect "institutionally reinforced obligations" to defer to the community. He also criticizes textbook advice "to strictly avoid tentative expressions altogether" [guide/analytic]. — [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf)
- Hyland's larger 56-article, eight-discipline corpus: about 14.6 hedges per 1,000 words (~85 per paper; most frequent forms may, would, possible). Soft fields (philosophy, marketing, sociology, applied linguistics) have the highest hedge density, and philosophy is reported at almost four times some hard fields [corpus; through search snippets of Hyland papers, exact table unverified]. — [Hyland, Discourse Studies 2005 (PDF copy)](https://www.everettsd.org/cms/lib/WA01920133/Centricity/Domain/965/hyland.pdf); [Hyland, Talking to the Academy](https://www.academia.edu/7567242/Talking_to_the_Academy_Forms_of_Hedging_in_Science_Research_Articles)
- Sociology research articles from 2015: 14.87 hedges per 1,000 words (Hyland & Jiang 2016, as reported) [corpus, secondary]. — [Tandfonline: Hedging practices in soft science RAs](https://www.tandfonline.com/doi/full/10.1080/23311983.2023.2249630)
- Boosters in Results/Discussion sections: soft fields 62.7 vs hard 38.76 per 1,000 words in one Hyland-framework study. These are much higher than other studies report, so counting methods differ [corpus, secondary; treat with caution]. — [Interactional metadiscourse markers in RA results and discussion](https://www.researchgate.net/publication/285942478_Interactional_metadiscourse_markers_in_academic_research_article_result_and_discussion_sections)
- Counting methods vary (single-word lists vs broader "devices"), which explains differences between figures such as 14.6 and 20.6 per 1k [analytic]. — [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf)

**AI slop in scientific prose**
- Kobak et al., "Delving into LLM-assisted writing in biomedical publications through excess vocabulary" (14 to 15M PubMed abstracts, 2010-2024): excess-word ratios for 2024 include "delves" r=28.0, "underscores" r=10.9 and "showcasing" r=10.2. Lower bound of LLM-processed 2024 abstracts: at least 10% in earlier arXiv versions, 13.5% in a later version per an aggregator, and up to 30-40% in some subcorpora. Versions conflict [corpus]. — [arXiv 2406.07016](https://arxiv.org/abs/2406.07016v5); [Language Log summary](https://languagelog.ldc.upenn.edu/nll/?p=64877)

### Inferences
- An agentless-passive cap derived from corpus norms would be well above 8/1k. If academic prose has ~25% passive finite verbs and roughly 80-100 finite verbs per 1,000 words (my rough assumption, not sourced), typical published academic prose carries ~20-25 passives per 1k. The current academic 8/1k cap is closer to what Nature and APA prescribe than to what is published. Choose deliberately: a "prescriptive" academic profile (cap ~8-10, citing Nature/APA) or a "descriptive" one (cap ~15-20, citing LGSWE).
- Hedging: a profile that treats hedges as slop will mis-flag good science. Corpus baselines are ~15-21/1k overall, ~36/1k in Discussion and ~20/1k in Intro and Results. Hedge allowance in academic should be at least ~2x the general default. Hyland's 43% clustering figure means a "stacked hedge" rule should target only redundant same-proposition stacks ("may possibly", "could potentially suggest", "it might perhaps"), not two hedges in one sentence.
- AI-damaging patterns specific to science: excess-vocabulary words (delve, underscore, showcase, intricate, pivotal, notably, "a comprehensive"); boosters without evidence ("clearly demonstrates", "groundbreaking", "novel" stacked); claims with no citation; and generic hedges with no epistemic target ("it is important to note that"). Hedges attached to a specific claim are legitimate.
- Tense by section is a checkable genre rule: Methods and Results in past tense, established knowledge and Discussion generalizations in present. This is standard style-guide advice but was not fetched this session (see Gaps). A heuristic check: share of past-tense finite verbs in a "Methods" headed section < ~50% → flag.

### Gaps
- IMRaD section-content requirements and abstract structure (structured abstracts in AMA/CONSORT; Nature's ~150-200-word unreferenced summary paragraph) were not fetched. The Nature formatting guide redirected to login. Word limits are unverified.
- AMA Manual of Style, ACS Style Guide and CSE positions on voice and first person: not retrieved.
- Tense-by-section conventions: a standard teaching claim, but no primary source was fetched (a Geoff Hart article surfaced in results but was not read: [geoff-hart.com](https://geoff-hart.com/articles/2019/past-tense.html)).
- Hyland's self-mention ("we/I") frequencies by discipline (Hyland 2001, "Humble servants of the discipline?") and the full Metadiscourse (2005) disciplinary table for hedges, boosters and self-mentions were not retrieved.
- Nominalization frequency norms in academic prose (Biber & Gray on noun-phrase complexity) were not retrieved, so no corpus number backs the 12/1k nominalization cap.
- Swales CARS model and Schimel's Writing Science: not retrieved.

## Technical documentation conventions (Google, Microsoft, Apple, Diátaxis, procedures)

### Takeaway
Developer-documentation guides converge on active voice, second person ("you", not "we"), present tense, conversational but not frivolous tone, numbered lists for sequences with conditions before instructions, and avoiding opinionated ease words (simple, simply, easy, easily, quick, quickly). Diátaxis adds that conventions differ by document type: tutorials may use a learner-facing "we", reference is neutral and austere, and explanation may be discursive and opinionated. A single "technical" profile is too coarse.

### Cited Findings
- Google developer documentation style guide highlights: "Be conversational and friendly without being frivolous"; "Use active voice: make clear who's performing the action"; "Use second person: 'you' rather than 'we'"; "Don't pre-announce anything in documentation"; "Put conditions before instructions, not after"; "Use numbered lists for sequences"; "Use unambiguous date formatting"; "Use serial commas" [guide]. — [Google style guide highlights](https://developers.google.com/style/highlights)
- Google voice page: "In general, use active voice." Passive is acceptable "To emphasize an object over an action", "To de-emphasize a subject or actor", or "If your readers don't need to know who's responsible for the action" [guide]. — [Google style guide: Active voice](https://developers.google.com/style/voice)
- Google's inclusive-documentation page flags "simple, simply, easy, easily, and quick, quickly" because they "introduce an opinion that might not reflect the user's experience". Its example rewrites "Simply open the configuration file to quickly add your custom key" [guide]. — [Google: Write inclusive documentation](https://developers.google.com/style/inclusive-documentation)
- A third-party copy of Google's voice-and-tone guidance lists "simply", "It's that simple", "It's easy" and "quickly in a procedure" as phrases to avoid [guide, secondary]. — [Slab copy of Google voice and tone](https://slab.com/library/examples/google-voice-and-tone)
- Microsoft: start statements with a verb; edit out "you can"; avoid "there is/are/were"; use contractions; sentence-style capitalization; no period at the end of headings; "Shorter is always better" [guide]. — [Microsoft Writing Style Guide, Top 10 tips](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)
- Diátaxis: four types. Tutorials ("A tutorial is a lesson"; learner-facing "we", e.g. "Here, we use HTTPS because it's safer"; minimal explanation). How-to guides (a real-world goal for a competent user; serve work). Reference ("free of distraction and interpretation", "Reference material is neutral"; structure mirrors the product). Explanation ("provide context and background", "can contain opinions and take perspectives") [guide]. — [Diátaxis: Start here](https://diataxis.fr/start-here/)
- Disagreement: Google says "you" rather than "we", but Diátaxis models "we" in tutorials. The conflict resolves by document type [guide]. — [Google highlights](https://developers.google.com/style/highlights); [Diátaxis](https://diataxis.fr/start-here/)

### Inferences
- Procedures are the most linter-checkable genre structure. Checkable rules: numbered-list items should begin with an imperative verb (spaCy: first token VB with no subject); one action per step (flag list items with 2+ imperative verbs joined by "and then"/", then" or more than one sentence of instruction); a condition clause ("if/when/to ...") should come before the imperative, not after; no "please"; no ease words (simply, just, easy, easily, quick, quickly, obviously, of course); no future tense for system behaviour ("will display" → "displays"); no "we" outside tutorials.
- The existing technical profile's choice to loosen construction (x1.5) on the theory that "passive voice is normal in runbooks" contradicts Google and Microsoft, which both say active voice by default. Passive is sanctioned only when the actor is unknown or irrelevant ("The file is created"). A sourced technical profile should keep passive-agentless at the general default, or relax it only for reference pages.
- Disabling long-sentence for technical contradicts Microsoft's "Shorter is always better" and Google's conversational aim. Code identifiers and paths inflate token counts, so a better sourced choice is a length rule that ignores code spans, not disabling it.
- AI-slop patterns that hurt docs most: ease words, "In this guide, we will explore…" pre-announcements (Google: don't pre-announce), "It's important to note that", marketing adjectives (powerful, seamless, robust), restating the heading, and explanation mixed into how-to steps (Diátaxis type mixing).

### Gaps
- Exact Google pages on tense ("use present tense"), procedures (one action per step, imperative), and the word-list entries for "just" and "please" were not fetched. Those specifics are standard but unverified here.
- Apple Style Guide and Write the Docs guidance: not retrieved.
- No numeric sentence-length or readability-grade target found in Google or Microsoft guides (Microsoft gives only "Shorter is always better").
- No corpus frequency data on passive or second-person rates in published technical documentation was found.

## Quantitative targets by genre (consolidated)

### Takeaway
Few authorities give hard numbers. The firmest are sentence-length averages (business 15-20 words), corpus passive shares (academic ~25% of finite verbs, news ~15%, conversation ~2%), and hedge densities (research articles ~15-21/1k overall, 36/1k in Discussion, ~3.6/1k in Methods). There are no sourced readability grade bands for any genre in what I retrieved.

### Cited Findings
| Measure | Genre | Value | Type | Source |
|---|---|---|---|---|
| Avg sentence length | Business/legal | ~20 words | guide | [LawProse #269](https://lawprose.org/lawprose-lesson-269-average-sentence-length/) |
| Avg sentence length | Army/BLUF | ~15 words (inconsistent) | guide, unverified | [JMU handout](https://www.jmu.edu/uwc/tutor-resources/MSL202L15%20Writing%20in%20the%20Army%20Style.pdf) |
| Max sentence length | Amazon (secondary) | <30 words | guide, unverified | [swipefile](https://swipefile.com/amazons-internal-writing-advice) |
| Passive share of finite verbs | Academic prose | ~25% | corpus | [Longman Student Grammar](https://vdoc.pub/documents/longman-student-grammar-of-spoken-and-written-english-4gkoo039ija0) |
| Passive share | News | ~15% | corpus, OCR-uncertain | [LGSWE copy](https://epdf.pub/longman-grammar-of-spoken-and-written-english.html) |
| Passive share | Conversation | ~2% | corpus, OCR-uncertain | same |
| Hedges per 1k words | Biology RAs (26 papers) | 20.6 overall; Disc 36; Intro 20; Results 20; Methods ≈3.6 | corpus | [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf) |
| Hedges per 1k words | 8 disciplines (56 papers) | ~14.6 | corpus, via snippet | [Hyland 2005 PDF](https://www.everettsd.org/cms/lib/WA01920133/Centricity/Domain/965/hyland.pdf) |
| Hedges per 1k words | Sociology 2015 | 14.87 | corpus, secondary | [Tandfonline](https://www.tandfonline.com/doi/full/10.1080/23311983.2023.2249630) |
| Hedge clustering | Biology RAs | 43% of hedges share a sentence with another | corpus | [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf) |
| AI vocab excess | PubMed 2024 | delves r=28.0; underscores 10.9; showcasing 10.2 | corpus | [Kobak et al.](https://arxiv.org/abs/2406.07016v5) |

### Inferences
- Readability grade bands in the profiles (e.g. marketing 7-10) cannot be backed by the genre authorities retrieved here. They should be labelled as opinion, or sourced from the plain-language researcher's material.

### Gaps
- No sourced paragraph-length targets for any genre.
- No corpus first-person rates by genre.
- No nominalization rates by genre (Biber & Gray not retrieved).

## Other genres (brief): news and legal

### Takeaway
News has a passive share between conversation and academic prose (~15% of finite verbs, per LGSWE) and a structural convention (the inverted pyramid: the most important facts first) that parallels BLUF. Legal plain-language guidance (Garner) shares business's ~20-word average.

### Cited Findings
- News passive share ~15% of finite verbs [corpus, OCR-uncertain]. — [LGSWE copy](https://epdf.pub/longman-grammar-of-spoken-and-written-english.html)
- Legal: Garner's Legal Writing in Plain English puts the target average at about 20 words. Other legal-writing experts say about 22 or under 25 [guide]. — [UT Austin legal writing blog](https://sites.utexas.edu/legalwriting/2021/05/01/sentence-length/)
- SEC disclosure (legal/financial hybrid): no multiple negatives, minimal defined terms, no legalese [guide/regulatory]. — [SEC handbook](https://www.sec.gov/pdf/handbook.pdf)

### Inferences
- A news profile would sit between general and academic on passive voice and would demand attributed quotes. Attribution is required in news, so "said" attributions to named sources should not trip weasel rules, while "sources say" / "experts believe" should.

### Gaps
- AP Stylebook rules (numerals, dates, attribution, inverted pyramid) were not retrieved this session. Any AP specifics are unverified.

## Profile implications

Settings are candidates. Each lists the rule, a suggested threshold, and its basis. "Inference" means derived by me from the cited sources, not stated by them.

### business (new profile; optional variant business-narrative)
- `weasel-attribution`: max 0/1k. Basis: Amazon "no weasel words" (secondary) ([Lasn](https://www.trevorlasn.com/blog/amazons-no-weasel-words-rule)); SEC "definite, concrete, everyday words" ([SEC](https://www.sec.gov/pdf/handbook.pdf)).
- Intensifiers/unquantified quantity words (significantly, substantially, most, many, nearly, vastly) with no number within the sentence: allowance multiplier 0.5 or lower. Basis: Amazon "replace adjectives with data" (secondary).
- `passive-agentless`: keep the general default or tighten (x0.75). Basis: SEC singles out "passive with agent deleted"; Army active-voice rule.
- `nominalization`: keep the default or tighten. Basis: SEC "Find hidden verbs" (-tion nouns with weak verbs).
- `long-sentence` / average sentence length: target average ≤20 words ([Garner/LawProse](https://lawprose.org/lawprose-lesson-269-average-sentence-length/)); individual max ~30 ([Amazon, secondary](https://swipefile.com/amazons-internal-writing-advice)). The Army 15-word average is an optional stricter setting (unverified).
- `corporate-vocabulary` / jargon: multiplier 0 to 0.5. Basis: SEC "Ruthlessly eliminate jargon and legalese"; Microsoft "Avoid jargon".
- New checkable rules:
  - **answer-first**: the first paragraph (or the first 2 sentences of an email) must contain a recommendation, request, decision or deadline marker. Flag throat-clearing openers ("I hope this email finds you well", "I wanted to reach out", "As you know"). Basis: BLUF ([JMU/Army](https://www.jmu.edu/uwc/tutor-resources/MSL202L15%20Writing%20in%20the%20Army%20Style.pdf)); Microsoft "Lead with what's most important".
  - **multiple-negatives**: flag 2+ negations in a clause ("not uncommon", "not unless ... not"). Basis: SEC Rule 421(d) "No multiple negatives".
  - **expletive openers**: flag "There is/are/were" sentence starts. Basis: Microsoft top-10.
  - **personal pronoun presence**: soft warning when a document over ~300 words contains no "you"/"we". Basis: SEC personal-pronoun guidance.
- Bullets: no penalty in `business`. In `business-narrative`, flag sections where bullets exceed ~30% of lines. Basis: Amazon narratively structured memos instead of slides ([Bezos 2017](https://www.aboutamazon.com/news/company-news/2017-letter-to-shareholders)). The threshold is inference. Note the opposite SEC advice ("Use bullets ... wherever possible").

### academic / scientific
- `passive-agentless`: two sourced options. (a) Prescriptive: ~8-10/1k (the current 8 is defensible), basis Nature "prefer ... active voice" and APA 7 (unverified). (b) Descriptive: ~15-20/1k, basis LGSWE ~25% passive finite verbs in academic prose (per-1k conversion is my inference). Recommend (a) for the whole document plus a section exemption: in sections headed Methods/Materials/Procedure/Experimental, disable or multiply passive by ≥3. Basis: CASRAI and Editage on passive in Methods.
- `hedges`: allowance multiplier ~2.0 to 2.5 relative to general prose; Discussion sections up to ~36/1k; Methods should be low (~4/1k). Basis: [Hyland 1995](https://files.eric.ed.gov/fulltext/ED390258.pdf) (20.6/1k overall; 36 Disc; ≈3.6 Methods), [Hyland 56-paper corpus](https://www.everettsd.org/cms/lib/WA01920133/Centricity/Domain/965/hyland.pdf) (~14.6/1k). Soft-science subprofiles (philosophy, sociology) could go higher (inference from Hyland's discipline spread).
- Stacked-hedge rule: flag only same-proposition redundancy (modal + hedge adverb on the same verb: "may possibly", "could potentially", "might perhaps"), not co-occurrence. Basis: Hyland's 43% same-sentence clustering is normal.
- Excess hedging in Methods: flag modals or epistemic adverbs in Methods sections above ~5/1k (inference from Hyland's 4% / one-tenth figure).
- `weasel-attribution`: keep 0. Add **uncited-claim** checks: "studies show", "research suggests", "it is well known", "evidence indicates" with no citation marker (bracketed number, (Author, Year), superscript) in the same or next sentence. Basis: academic citation norms. No primary source fetched; inference consistent with the current profile.
- AI-vocabulary rule: add a science-specific excess-word list with high weight: delve(s), underscore(s), showcasing, intricate, pivotal, notably, meticulous(ly), commendable. Basis: [Kobak et al.](https://arxiv.org/abs/2406.07016v5) ratios (delves 28.0, underscores 10.9, showcasing 10.2). The other words come from the same paper's excess list, but individual ratios were not verified here.
- Boosters: tighten unsupported boosters ("clearly demonstrates", "proves", "groundbreaking", "novel" in Results/Discussion without a figure or statistic nearby). Basis: Hyland's framework treats boosters as stance; thresholds unsourced (Gap).
- `nominalization` 12/1k: currently unsourced. Keep it, but label it opinion until Biber & Gray data is retrieved.
- First person: do not flag "we" in co-authored papers; flag "I" in multi-author papers and "the authors"/"this researcher" circumlocutions as optional style hints. Basis: APA 7 first-person guidance (unverified page) and Nature active-voice preference.
- Tense-by-section rule (checkable with spaCy morphology): Methods/Results mostly past tense; flag Methods with >50% present-tense finite verbs. Basis: standard convention, unverified (Gap).

### technical (revise existing)
- `passive-agentless`: do not loosen globally (remove or reduce the construction x1.5). Basis: Google "In general, use active voice" with narrow exceptions ([Google voice](https://developers.google.com/style/voice)); Microsoft. Optionally relax x1.5 only for reference pages (Diátaxis "Reference material is neutral").
- `long-sentence`: re-enable, excluding inline code, paths and URLs from token counts. Basis: Microsoft "Shorter is always better"; Google conversational tone. The threshold is unsourced; use the general default.
- `corporate-vocabulary` x0.5 is consistent with Microsoft "Avoid jargon"; also add marketing adjectives (powerful, seamless, robust, cutting-edge) at multiplier 0.
- New checkable rules:
  - **ease-words**: flag simple, simply, easy, easily, quick, quickly, just (as minimizer), obviously, of course. Basis: [Google inclusive documentation](https://developers.google.com/style/inclusive-documentation) (simple/simply/easy/easily/quick/quickly explicit; "just" unverified).
  - **step-imperative**: in numbered list items, first verb must be imperative (no subject). Basis: Google "Use numbered lists for sequences"; Microsoft "start each statement with a verb".
  - **one-action-per-step**: flag list items with ≥2 imperative verbs or ≥2 sentences of instruction (inference; Google procedures page not fetched).
  - **condition-first**: flag a step where an "if/when/before" clause follows the imperative. Basis: Google "Put conditions before instructions, not after".
  - **second-person**: flag "we" outside documents marked tutorial; flag "the user" where "you" fits. Basis: Google "'you' rather than 'we'"; Diátaxis allows "we" in tutorials.
  - **pre-announcement / future**: flag "will" for product behaviour and "In this guide we will ..." / "coming soon". Basis: Google "Don't pre-announce anything in documentation".
  - **you-can / there-is**: flag unnecessary "you can" and expletive "there is/are". Basis: Microsoft top-10.
  - **contractions**: do not flag. Microsoft encourages them.
- Subprofiles by Diátaxis type (tutorial / how-to / reference / explanation): explanation may relax hedges and opinion markers ("can contain opinions"); reference should disable second-person and conversational checks; how-to should flag explanatory digressions (e.g. "because"-clauses over N words inside steps). Basis: [Diátaxis](https://diataxis.fr/start-here/).

### news (optional)
- `passive-agentless`: between general and academic (~15% passive share in news vs ~25% academic and ~2% conversation, per [LGSWE](https://epdf.pub/longman-grammar-of-spoken-and-written-english.html)). Suggested multiplier ~1.5x general (inference).
- Weasel attribution: strict ("sources say", "experts believe" flagged), but named-source "said" never flagged. Lede check: the first sentence should contain who/what plus a number, date or place (inverted pyramid; AP not retrieved, unverified).

### legal / disclosure (optional)
- Average sentence ≤20 words ([Garner via UT](https://sites.utexas.edu/legalwriting/2021/05/01/sentence-length/)); multiple-negatives rule; legalese list (hereto, herein, aforementioned, pursuant to, notwithstanding) at multiplier 0; personal pronouns encouraged ([SEC](https://www.sec.gov/pdf/handbook.pdf)).

### Cross-genre notes for the existing profiles
- **marketing** hedges x2.0: no genre source supports looser hedging in marketing. Amazon and SEC data-over-adjectives guidance cuts the other way. Grade 7-10 is unsourced here.
- **fiction**: outside this scope; LGSWE shows fiction as a distinct register, but no fiction-specific numbers were retrieved.
- Section awareness (detecting the Methods/Discussion/Procedure headings) is the single most valuable capability these sources imply. Every strong quantitative finding (Hyland's section densities, passive in Methods, imperative in procedures) is section-specific, not document-wide.
