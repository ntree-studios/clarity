# Discourse-level failures of LLM prose: paragraphs, sections, documents

Scope note: this covers failures above the sentence, beyond what clarity already measures (sentence tics, section restatement, sentence overlap, novelty rate, paragraph length distribution, paragraph-opener repetition, heading hierarchy, list parallelism, sentence-length variance, lexical diversity). Each item ends with a proposed **Signal**: something countable that a deterministic spaCy linter could compute. Example passages marked *(illustrative)* are written by the researcher to show the pattern. They are not quoted from a corpus. Quoted passages carry their source.

Evidence base in one line: the strongest empirical work is Reinhart et al. (PNAS 2025, Biber features), Jiang & Hyland (metadiscourse in 145 vs 145 essays), Herbold et al. (large-scale essay comparison), Shaib et al. (2025, slop taxonomy with copy-editor span annotation), Bharadwaj et al. (2025, "Flattery, Fluff, and Fog" reward-model biases), LMSYS style control, and homogenization studies. Most practitioner "tells" lists (Wikipedia, blogs, teacher guides) are informed observation, not measurement.

---

## 1. Padding and low information density (preambles, restating closers, moral endings, signposting, throat-clearing)

### Takeaway
Copy-editors treat low information density and irrelevance as the strongest predictors of a "slop" verdict. Simple proxies for these, such as word count, compression ratio and template counts, did not predict that verdict on their own. Padding is better detected by position (first and last paragraph, last sentence of each paragraph) plus phrase families plus comparison against the body's content, not by raw length. Training explains where padding comes from: reward models and human raters reward length, which pushes models toward preambles and recap closers.

### Cited Findings
- Shaib, Chakrabarty, Garcia-Olano & Wallace's slop taxonomy defines **Density (IU1)** as "substantive content relative to length; low-density text is verbose but says little, or relies on generic statements." It also defines **Verbosity (SQ5)** as excessive wordiness relative to the information conveyed. Three professional copy-editors annotated 150 news articles and 100 RAG QA passages. About 34–35% of samples were judged slop. — [Shaib et al., Measuring AI "Slop" in Text, arXiv 2509.19163](https://arxiv.org/html/2509.19163v2); [Northeastern Khoury news](https://www.khoury.northeastern.edu/?p=58466)
- In logistic regression, all seven annotated codes predicted the binary slop label. The strongest overall were **Relevance (β≈0.06), Density (β≈0.05) and Tone (β≈0.05)**. The number of annotated problem spans correlated with the slop label at ρ = 0.70 (news) and 0.63 (all). — [Shaib et al.](https://arxiv.org/html/2509.19163v2)
- Simple automatic proxies did **not** reach significance as standalone predictors of slop: word count (verbosity), compression ratio (repetition), templates-per-token (templatedness) and Gunning-Fog. A combined linear model reached AUPRC 0.52–0.55 against a prevalence of about 0.25. LLM judges (GPT-5, DeepSeek-V3, o3-mini) had κ ≈ 0 with humans and flagged only 3–8% of texts, against 34% for humans. — [Shaib et al.](https://arxiv.org/html/2509.19163v2)
- Length is the dominant style factor in human preference votes. LMSYS style control found coefficients of 0.249 for answer length against 0.031 (lists), 0.024 (headers) and 0.019 (bold). A later sentiment-control model gave length 0.238. — [LMSYS style control blog](https://lmsys.org/blog/2024-08-28-style-control); [LMArena sentiment control](https://news.lmarena.ai/sentiment-control)
- Singhal et al. report that a purely length-based reward reproduces most of the gains of learned RLHF reward models. PPO noticeably lengthens outputs. This is the standard citation for verbosity as reward hacking. — [Singhal et al., "A Long Way to Go," cited in ODIN arXiv 2402.07319](https://arxiv.org/pdf/2402.07319); [reward-hacking survey arXiv 2604.13602](https://arxiv.org/pdf/2604.13602)
- Bharadwaj et al. name "Fluff" (verbose, uninformative responses) as one of five reward-model bias features. Reward models prefer verbose responses 60.1% of the time. Across all bias features, model preference conflicts with the human majority in 39.4% of evaluations. — [Flattery, Fluff, and Fog, arXiv 2506.05339](https://arxiv.org/html/2506.05339v2)
- Wikipedia's AI Cleanup guide documents several padding patterns:
  - Chatbot preambles and closers, e.g. "Here's a template for your wiki user page", "Would you like...", "I hope this helps", "let me know".
  - Knowledge-gap preambles, e.g. "While specific details are limited..." and "Below is a detailed overview based on available information:".
  - Section summaries, listed as a historical indicator.
  
  — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- Wikipedia also documents the **significance-ending paragraph**, which it calls "undue emphasis on significance and legacy." Watch phrases are "stands/serves as", "is a testament/reminder", "setting the stage for" and "key turning point". Its example: "marking a pivotal moment in the evolution of regional statistics in Spain." A related pattern ends a sentence with a **trailing participial clause** that adds faux analysis, e.g. "...reflecting its continued relevance in the regional and national transportation landscape". Watch words: highlighting, underscoring, contributing to, fostering, valuable insights. — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- Jiang & Hyland found that ChatGPT essays rely *more* on interactive metadiscourse, meaning transitions and endophoric markers ("as discussed above", "in the following section"). They rely *less* on interactional markers (hedges, boosters, attitude markers). Their summary: ChatGPT's "strength was structure." — [Jiang & Hyland, Rhetorical distinctions, ESP 2025 (UEA eprint)](https://ueaeprints.uea.ac.uk/id/eprint/99123)

Illustrative passages:
- Throat-clearing opener *(illustrative)*: "In today's fast-paced digital landscape, data privacy has become more important than ever. In this article, we will explore what data privacy means, why it matters, and how you can protect yourself."
- Moral or significance ending *(illustrative)*: "...The bridge opened in 1932. Ultimately, it stands as a testament to the region's enduring commitment to progress."
- Recap closer *(illustrative)*: "In conclusion, data privacy is a multifaceted issue that requires attention from individuals, companies, and governments alike. By understanding these key aspects, readers can better navigate the digital world."

### Inferences
- **Signal: preamble restatement.** Compute content-lemma Jaccard or containment between the prompt/title/H1 and the first paragraph. Separately, compute the share of first-paragraph content lemmas that reappear in the body. A first paragraph with high title overlap, low novelty and no numerals or proper nouns is throat-clearing.
- **Signal: forward signposting.** Count future and meta-discourse patterns per document: "(in) this (article|post|guide|section) (we|I) (will|'ll) (explore|discuss|examine|look at|delve)", "let's (dive|explore|take a look)", "below (is|are|we)", "the following". Use a spaCy Matcher on a lemma sequence: PRON + AUX(will) + VERB in {explore, discuss, examine, cover, delve, unpack} with DET "this" + NOUN in {article, guide, post, section} nearby. Threshold: more than 1 per document.
- **Signal: recap closer.** The last paragraph starts with a closer marker ("In conclusion", "In summary", "Overall", "Ultimately", "To sum up", "In short", "All in all") **and** its novelty rate against the preceding body is below a threshold. clarity already has novelty rate, so apply it specifically to the final paragraph, with an extra penalty for the closer marker.
- **Signal: significance tail.** For each paragraph's last sentence, flag it if it contains (a) a lexicon match {testament, pivotal, crucial, vital, underscore(s), highlight(s), legacy, landscape, enduring, broader, paving the way, setting the stage, continues to (evolve|thrive|shape)}, or (b) a sentence-final participial clause. For (b), use the dependency `advcl` with VBG head after a comma at sentence end. Also require (c) no numeral or PROPN token in the sentence. Report the share of paragraphs ending this way. A document where more than 30% of paragraphs end like this is templated. The threshold needs calibration.
- **Signal: chatbot residue.** Flag phrases such as "I hope this helps", "Let me know if", "Would you like me to", "Feel free to", "Here's a", "Great question", and "Certainly!" at the start of the document. These are near-deterministic.
- The Shaib finding that word count alone does not predict slop argues *against* a raw length rule. Padding rules should be positional and ratio-based: information per paragraph relative to the document.

### Gaps
- I found no study that measures how often LLM paragraphs end in a significance statement compared with human paragraphs. The evidence is Wikipedia editors' observation.
- Shaib et al. do not report per-code base rates for "preamble" or "closer" separately. Density is annotated at span level without a positional breakdown.

---

## 2. Genericity and lack of specificity (no numbers, names, dates or examples; abstract over concrete; claims true of any subject)

### Takeaway
The evidence is real but more mixed than folklore suggests. Instruction-tuned LLMs write in a noun-heavy, nominalized, "informationally dense" register (Biber features), yet they are more abstract and less personally anchored than students. Some studies even find LLMs use *more* numerals or concrete words, depending on genre and prompt. So a missing-numerals rule alone is a weak signal. "Generic" is best captured as substitutability: a sentence that would stay true if the topic noun were swapped. Combine this with low PROPN/NUM/DATE density and vague attribution.

### Cited Findings
- Reinhart et al. compared human texts with Llama 3 variants and GPT-4o continuations of the same human openings, using Biber's lexical, grammatical and rhetorical features. They found large differences, larger for instruction-tuned models than base models, persisting across model sizes. Instruction-tuned models keep a **noun-heavy, informationally dense style even when prompted to imitate informal writing**. — [Reinhart et al., arXiv 2410.16107 / PNAS 2025](https://arxiv.org/html/2410.16107v2); [CMU press release](https://www.eurekalert.org/news-releases/1074717)
- Herbold et al. compared argumentative essays by German high-school students with ChatGPT-3.5/4 essays rated by teachers. ChatGPT text had **more nominalizations and greater lexical diversity**, and fewer discourse and epistemic markers. Teachers rated the AI essays higher. — [Herbold et al., arXiv 2304.14276](https://arxiv.org/abs/2304.14276v1)
- Jiang & Hyland's synthesis of five studies describes ChatGPT essays as tidier, more formulaic, **more abstract**, and less personally invested. Authorial presence markers appeared 0 times in the ChatGPT essays against 85 in the student essays (as reported in secondary coverage). The "Taking a stance" study reports significantly fewer stance expressions, a narrower lexical repertoire, and weaker authorial presence. — [Jiang & Hyland engagement study (UEA)](https://ueaeprints.uea.ac.uk/97952/); [secondary summary with 0 vs 85 figure: popularai.org](https://www.popularai.org/p/how-teachers-spot-chatgpt-essays-without-a-detector) (secondary; check against the paper)
- Contrary evidence on concreteness: Zhou et al.'s Coh-Metrix comparison found ChatGPT scored **higher** than Chinese EFL learners on narrativity, word concreteness and referential cohesion, and lower on syntactic simplicity and deep cohesion. — [Zhou et al., arXiv 2303.11812](https://arxiv.org/abs/2303.11812)
- Contrary evidence on numbers: Muñoz-Ortiz et al. found LLM-generated news (from a headline plus opening words) uses **more numbers, symbols and auxiliaries**, and more pronouns, than human news. — [Muñoz-Ortiz, Gómez-Rodríguez & Vilares, Artificial Intelligence Review 2024 / arXiv 2308.09067](https://arxiv.org/abs/2308.09067v3)
- Bharadwaj et al. name "Fog" as a reward-model bias: vague responses that make many non-specific claims. "Vagueness (lack of specificity)" is one of five features reward models over-reward. Mean correlation of these features with human labels was r = −0.12, against r = +0.36 with a strong reward model's labels. — [Flattery, Fluff, and Fog, arXiv 2506.05339](https://arxiv.org/html/2506.05339v2)
- Wikipedia describes **"smoothing of specific facts"**: specific, unusual facts are replaced with generic positive statements, described as regression to the mean. It also flags **vague attributions** ("Observers have cited", "Experts argue", "Industry reports"), **vague connections** ("in connection with", "associated with"), and overgeneralizing one or two sources as widely held. — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- Teachers and educators repeatedly cite polished structure plus generic content as the main tell: "perfectly formed intros, subtopics, and conclusions, but [they] stay surface-level with generic claims or weak examples." This is anecdotal and often from detection-vendor blogs. — [techlearning.com](https://www.techlearning.com/how-to/6-ways-teachers-can-tell-students-are-using-ai); [Gizmodo, professor interview](https://gizmodo.com/the-biggest-signs-that-ai-wrote-a-paper-according-to-a-professor-2000634580)
- One essayist says the real giveaway is hollowness ("polished writing but relatively mundane ideas"), not surface tics. This is commentary. — [Carly, "Spotting machine-made prose"](https://carly.substack.com/p/spotting-machine-made-prose)

Illustrative passage *(illustrative)*: "Artificial intelligence plays a crucial role in many industries, driving innovation and improving efficiency. Experts agree that its impact will only continue to grow." Replace "Artificial intelligence" with "Cloud computing" or "Blockchain" and every claim still reads as true. That is the substitutability test.

### Inferences
- **Signal: specificity density per paragraph.** Count (NUM + DATE/TIME/MONEY/PERCENT/QUANTITY entities + PROPN tokens not in the title + quoted spans + code spans) per 100 tokens. Flag paragraphs with zero of these that are longer than N tokens. Report the document share of "zero-anchor" paragraphs. This uses relative, within-document comparison, because the Muñoz-Ortiz result shows absolute numeral rates can be higher in LLM text.
- **Signal: vague-quantifier and vague-agent rate.** Count lemmas such as {many, various, numerous, several, countless, a wide range of, a variety of, diverse}. Count subjects that are vague collective NPs such as {experts, studies, research, observers, critics, industry reports, many people}, where the NP has no PROPN modifier and there is no citation or link in the sentence. Use spaCy `nsubj` whose head lemma is in the vague-agent list and has no `compound`/`appos` PROPN child.
- **Signal: abstract-noun ratio.** Use the Brysbaert et al. concreteness norms (40k English lemmas, freely available). Compute mean concreteness of NOUN tokens per paragraph and the share of nominalizations (suffixes -tion, -ment, -ness, -ity, -ance, -ence). Herbold and Reinhart support nominalization as a discriminator. Zhou et al. warn that word-level concreteness can go the other way, so use it as a paragraph-relative outlier flag, not a global threshold.
- **Signal: substitutability.** For each sentence, compute the proportion of content lemmas that are topic-specific, meaning they appear in the title/headings or are PROPN/NUM, against the proportion that are generic high-frequency "evaluation" lemmas {crucial, important, significant, key, role, impact, landscape, innovation, efficiency, growth, various, ensure, enhance}. Flag sentences where topic-specific share is 0 and the generic-evaluation share is high. A deterministic proxy is the template "X plays a (crucial|vital|key|significant|pivotal) role in".
- **Signal: example deficit.** Count example markers per section ("for example", "for instance", "such as", "e.g.", "consider", a colon followed by a list of PROPN). Sections with claims but zero examples and zero anchors are generic.

### Gaps
- I found no published study that directly measures named-entity or numeral density across matched human vs. instruction-tuned LLM expository prose. The closest evidence (Muñoz-Ortiz) is news continuation, which points the opposite way, so this is an open calibration question.
- No study operationalizes the "substitutability" test. It is the researcher's proposal.

---

## 3. Topic drift and failure to stay on subject

### Takeaway
Copy-editors rated **Relevance** (content not addressing the prompt or task) as the single strongest predictor of slop. Inter-annotator agreement on it was only moderate. LM research shows models capture local topicality but struggle to maintain long-range structure. Drift can be measured deterministically as lexical or embedding distance between a unit's anchor (heading or opening sentence) and its body.

### Cited Findings
- Shaib et al. define **Relevance (IU2)** as whether content addresses the prompt or task. Their example is a general exercise-benefits sentence given in reply to a question about marathon times. Relevance had the largest coefficient (β≈0.06) predicting slop. Code-level agreement for Relevance, Density and Coherence fell in a "moderate-to-challenging" band, below the AC1 0.5 threshold. — [Shaib et al.](https://arxiv.org/html/2509.19163v2)
- Deng, Kuleshov & Rush ("Model Criticism for Long-Form Text Generation", EMNLP 2022) tested discourse coherence, coreference and topicality. They found transformer LMs "are able to capture topical structures but have a harder time maintaining long-range structure", and suggested explicit section topic markers help. — [arXiv 2210.08444](https://arxiv.org/pdf/2210.08444); [ACL Anthology](https://aclanthology.org/2022.emnlp-main.815)
- One deterministic drift metric from the literature is topic drift = 1 − Jaccard overlap of content words (nouns, verbs, adjectives) between the first and last thirds of an output. — [Projected Autoregression preprint, arXiv 2601.04854](https://arxiv.org/pdf/2601.04854) (preprint)
- Liu et al. argue that lexical and semantic overlap metrics (BLEU, ROUGE, BERTScore) cannot capture discourse coherence, and propose a positional discourse coherence metric (PDD). — [arXiv 2402.10175](https://arxiv.org/pdf/2402.10175)
- Wikipedia notes that LLM articles situate subjects in broader "debates" or trends ("has shaped emerging policy discussions") and pad notability with lists of coverage. Both move away from the article's subject. — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)

Illustrative passage *(illustrative)*: under the heading "How to replace a bike chain": "Cycling is one of the most popular forms of exercise worldwide, offering benefits for cardiovascular health, mental well-being, and the environment. Regular maintenance is essential for any cyclist..." This is adjacent-topic answering. The heading's key lemmas (replace, chain) do not appear until paragraph 3.

### Inferences
- **Signal: heading–body alignment.** For each section, compute the share of the heading's content lemmas that appear in the section body, and the position of their first appearance (token offset or sentence index). Flag when the heading's head noun does not appear in the first two sentences, or when overall overlap is below a threshold. If clarity allows a small static model, add spaCy `en_core_web_md` vector cosine between the heading and each paragraph centroid. That is still deterministic.
- **Signal: paragraph drift.** Compute cosine or Jaccard between the first sentence (topic sentence) and each later sentence. Flag paragraphs where similarity decays monotonically and the last sentence is less similar to the first than to the *next* paragraph's first sentence. A cheaper version is first-third vs last-third Jaccard per paragraph or per section, as in arXiv 2601.04854.
- **Signal: answer-first check, for Q&A/README/doc contexts.** If the document has a question-like title or H1 ending in "?" or starting "How/What/Why", check whether the title's key lemmas plus an answer-type cue (NUM for "how many", a VERB imperative for "how to") occur in the first paragraph.
- **Signal: broadening sentences.** Flag sentences whose subject is a generic superordinate with no lemma overlap with the section heading, e.g. "society", "the world", "industries", "the broader landscape", "the future". Use a lexicon plus heading-overlap = 0.

### Gaps
- No found study quantifies how often LLM sections mismatch their headings compared with human sections.
- Relevance is the least reliable code for humans to annotate, so any deterministic proxy will be noisy.

---

## 4. Templated structure (uniform paragraph shape, claim→explanation→significance, over-headed and over-bulleted content, bold lead-ins, listicles, symmetric sections, Key Takeaways, FAQ appendages)

### Takeaway
Structure is the best-evidenced cluster. Reward models prefer list-structured responses about 89.5% of the time, and GPT-4-Turbo judges prefer bolded responses about 89.5% of the time. Human Arena voters show smaller but positive effects for headers, lists and bold. AI-assisted student essays lost 70–78% of the variance in their "cohesion architecture." Wikipedia editors call out rigid article outlines (Challenges / Future Prospects), "X and Y" headers, title case and bold lead-in lists. Templatedness is countable as low between-unit variance in shape and as high markup density relative to prose.

### Cited Findings
- Bharadwaj et al.: reward models prefer **structured (list-formatted) responses in 89.5%** of comparisons, against a weaker human preference. — [Flattery, Fluff, and Fog, arXiv 2506.05339](https://arxiv.org/html/2506.05339v2)
- "From Lists to Emojis: How Format Bias Affects Model Alignment" reports GPT-4-Turbo as judge had an **89.5% win rate for bold responses over plain counterparts**, plus biases for lists, links and emojis. It shows format bias can be exploited in alignment. — [arXiv 2409.11704](https://arxiv.org/html/2409.11704v2)
- In human Arena votes, markdown effects are positive but second-order to length: headers 0.024–0.029, lists 0.020–0.031, bold 0.0135–0.019. Emoji count was slightly negative (−0.0039). — [LMSYS](https://lmsys.org/blog/2024-08-28-style-control); [LMArena sentiment control](https://news.lmarena.ai/sentiment-control)
- Inoshita et al. (2026 preprint, 6,875 essays across Human-only, AI-only and three Human+AI conditions) found quality gains co-occur with homogenization. **Cohesion architecture lost 70–78% of its variance**, while perspective plurality grew more diverse. More specific prompts reversed homogenization on argument depth. — [arXiv 2603.21228](https://arxiv.org/abs/2603.21228) (preprint; metrics not detailed in abstract)
- Padmakumar & He (ICLR 2024): essays co-written with InstructGPT, but not base GPT-3, were more similar to each other and had the least lexical and content diversity. The cause was the model's contributed text, not changes in user style. — [arXiv 2309.05196](https://arxiv.org/html/2309.05196v3)
- Moon et al.'s three preregistered studies of 2,200 college admissions essays found a diversity gap that parameter or prompt changes to increase GPT's creativity did not close. — via [Stanford SCALE repository](https://scale.stanford.edu/ai/repository/homogenizing-effect-large-language-models-llms-creative-diversity-empirical) (summary page)
- Wikipedia lists structural signs:
  - A rigid outline ending in "Challenges" and "Future Prospects" sections.
  - Generic "X and Y" headers ("Challenges and Future Directions").
  - An "Awards and recognition" heading that is "nearly ubiquitous" in AI articles.
  - Title case headings.
  - Excessive bold in prose.
  - **Vertical lists with bold inline headers**, e.g. "**Standard Rotary Saws**: Typically used for drywall and light materials."
  - Emoji at the start of headings or list items.
  - `---` dividers, multiple H1s.
  - Outline-style conclusions: "Despite these challenges, [subject] continues to thrive."
  
  — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- Shaib et al. define **Templatedness (SQ2)** as formulaic structures, predictable formatting and repeated transitions. Their example is parallel "Dr. X, a researcher at Y, found that…" sentences. On MS MARCO QA, "Structure" was among the strongest predictors of slop, with code-level AC1 of 0.51. Templates-per-token alone was not significant. — [Shaib et al.](https://arxiv.org/html/2509.19163v2)
- Teachers report a five-paragraph default (intro, three body paragraphs, conclusion) even when the prompt does not ask for it. This is anecdotal or vendor-sourced. — [techlearning](https://www.techlearning.com/how-to/6-ways-teachers-can-tell-students-are-using-ai); [Reason, on the five-paragraph essay](https://reason.com/2024/05/30/long-live-the-five-paragraph-essay/)
- Rhetorical devices recur at the paragraph scale: compulsive parallelism, explicit antithesis ("it's not X, it's Y") and tricolon. Gorrie's explanation is that the models lack "the taste to know when to deploy these techniques." Commentary. — [Colin Gorrie, "Why ChatGPT writes like that"](https://www.deadlanguagesociety.com/p/rhetorical-analysis-ai)
- The "not just X, but Y" construction reportedly appeared in about 6% of ChatGPT messages in a Washington Post analysis. This was reported secondhand and not verified. — [Decrypt](https://decrypt.co/348923/5-biggest-tells-something-written-ai)

Illustrative skeleton, repeated per paragraph *(illustrative)*: "[Topic sentence: X is important.] [Explanation: This is because X does A, B, and C.] [Significance: Ultimately, X plays a pivotal role in Y.]" Three sentences, roughly equal length, the third with a significance lexeme, repeated across 4–6 paragraphs.

### Inferences
- **Signal: paragraph shape fingerprint.** Encode each paragraph as a short tuple: (sentence count bucket; first-sentence type, e.g. copular/definitional vs. other; whether the last sentence has a significance lexeme or participial tail; whether it has an example marker; whether it has a numeral or PROPN). Compute the entropy or the modal-shape share across paragraphs. A document where more than 60% of body paragraphs share one fingerprint is templated. This extends the existing paragraph length distribution and opener repetition rules from length to shape.
- **Signal: sentence-count uniformity.** Compute the coefficient of variation of sentences per paragraph, as distinct from token length, which clarity already tracks. LLM outputs often cluster at 3–4 sentences.
- **Signal: markup density.** Compute (bold spans + list items + headings) per 100 prose tokens. Compute the share of list items that are complete sentences of 15 tokens or more ("prose in bullets"). Compute the share of list items matching `^\*\*[^*]+\*\*:` ("bold lead-in"). Flag a document where more than 50% of list items use bold lead-ins, or where headings occur every fewer than 80 words.
- **Signal: over-sectioning.** Compute words per section, and flag sections with fewer than 2 paragraphs, or a single paragraph under 60 words, under their own heading. Flag heading-to-paragraph ratios near 1.
- **Signal: boilerplate section names.** Use a lexicon of heading strings: {Conclusion, Key Takeaways, Final Thoughts, Summary, FAQ, Frequently Asked Questions, Challenges and Future Directions, Future Prospects, Overview, Introduction, Why It Matters, Benefits, Best Practices, Awards and Recognition}. Also flag "X and Y" two-noun headings and title case headings. Score the count, plus position: a FAQ or Key Takeaways section after a Conclusion is an appendage.
- **Signal: symmetric sections.** Compute the CV of word counts and of paragraph counts across sibling sections (same heading level). Compute the CV of list lengths, where "exactly 3 or 5 items everywhere" is a signal. Count the share of lists with exactly 3 items (tricolon) and within-sentence triads: coordinated NPs or ADJs with three conjuncts, via spaCy `conj` chains of length 3.
- **Signal: antithesis density.** Count matches per 1,000 words for "not (just|only|merely) X(,| but) (also)? Y", "isn't X(,|;|—) it's Y", "less about X and more about Y", "rather than", "should be treated as … rather than …". Wikipedia notes the last as new in mid-2026 output. These are sentence-level patterns, but density and clustering across paragraphs is the discourse-level signal.

### Gaps
- No found study directly measures human vs. LLM distributions of sentences per paragraph or of bold lead-in lists in non-chat prose such as docs or READMEs.
- The Inoshita "cohesion architecture" metric is not described in the abstract.

---

## 5. Low burstiness and uniform rhythm; reduced variance at paragraph level

### Takeaway
"Burstiness" in the detection literature means variation in *perplexity* across a document, not sentence length. GPTZero says it no longer uses perplexity or burstiness for detection (since autumn 2023) and keeps them only as explanations. A deterministic, model-free linter can approximate the idea with between-paragraph variance of cheap per-paragraph features. Strong stylometric evidence supports reduced variance in LLM text: narrower sentence-length distributions and homogenized structure. Model-based detectors (DetectGPT, Binoculars) rely on token probabilities, which a spaCy linter cannot reproduce.

### Cited Findings
- GPTZero defines perplexity as how likely an AI model would have chosen the exact same words, with "above 85" more likely human. It defines burstiness as "a measure of how much writing patterns and text perplexities vary over the entire document," with no set threshold. GPTZero says it moved to a deep-learning classifier and stopped using these for detection in autumn 2023. — [GPTZero support: interpreting burstiness/perplexity](https://support.gptzero.me/hc/en-us/articles/15130070230551-How-do-I-interpret-burstiness-or-perplexity); [GPTZero technical report arXiv 2602.13042](https://www.alphaxiv.org/abs/2602.13042)
- Binoculars (Hans et al., 2024) uses two LLMs to compute a cross-perplexity score from their agreement. — summarized in [arXiv 2406.18259](https://arxiv.org/pdf/2406.18259v1); original [Hans et al., arXiv 2401.12070](https://arxiv.org/abs/2401.12070) (not re-fetched this session)
- DetectGPT (Mitchell et al., 2023) relies on probability curvature: machine text sits near local maxima of model log-probability. — [arXiv 2301.11305](https://arxiv.org/abs/2301.11305) (from prior knowledge, not re-fetched this session)
- Muñoz-Ortiz et al.: human news "exhibit[s] more scattered sentence length distributions" than LLM output. Human text also has more vocabulary variety and shorter constituents. Differences between LLMs and humans are larger than differences among LLMs. — [arXiv 2308.09067](https://arxiv.org/abs/2308.09067v3)
- Reinhart et al.: Biber-feature differences are robust and larger for instruction-tuned models. A 2026 follow-up on RAID found instruction-tuned models cluster apart from both base models and humans, and that genre matters more than authorship. — [Reinhart et al.](https://arxiv.org/html/2410.16107v2); [Interpretable Stylistic Variation, arXiv 2604.14111](https://www.alphaxiv.org/abs/2604.14111)
- Homogenization at the document and corpus level appears in Inoshita et al. (70–78% variance loss in cohesion architecture) and in Padmakumar & He. — see section 4 citations.
- Wikipedia cautions that detectors have "non-trivial error rates". Human detection is near chance in some studies (57% for AI, 64% for human texts in one), while expert annotators reached 90% with 3.3% false positives in a preprint. — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)

### Inferences
- **Signal: paragraph-feature variance (a "burstiness proxy").** For each paragraph compute a vector: mean sentence length, sentence-length SD, type-token ratio, nominalization rate, specificity density (section 2), mean word frequency rank (surprisal proxy via `wordfreq` Zipf), and punctuation mix (questions, parentheses, colons). Report the CV of each across paragraphs, or the mean pairwise distance. Low between-paragraph variance means a uniform rhythm. This moves the existing sentence-length variance up one level.
- **Signal: sentence-type mix per document.** Compute the share of interrogatives, imperatives, fragments (no ROOT verb), and parentheticals. Human essays use more questions and asides (Jiang & Hyland engagement findings, section 6). A document with zero questions, zero parentheticals and zero fragments across 800 or more words is uniform.
- **Signal: word-rarity burstiness.** Without an LM, use a Zipf frequency lexicon to compute the per-sentence mean of the rarest content word. Variance across sentences approximates perplexity burstiness.
- Caveat for rule design: rhythm uniformity is a weak, genre-sensitive signal, and the Biber follow-up shows genre dominates. Calibrate thresholds per document type (README vs. essay vs. docs).

### Gaps
- No found study reports paragraph-level (as opposed to sentence- or token-level) variance metrics for human vs. LLM text.
- The DetectGPT and Binoculars details here come from prior knowledge and secondary summaries, not fetched this session.

---

## 6. Hedged, non-committal conclusions; both-sidesing; refusal to rank; sycophancy

### Takeaway
The evidence pulls in two directions. Corpus studies find ChatGPT essays use *fewer* hedges, boosters, attitude markers and stance expressions than students, so they read as impersonal rather than hedgy. Separately, models over-produce **knowledge-gap disclaimers**, "it's important to note" caveats, and balanced "on the other hand" structures, while reward models over-reward vagueness and flattery. The non-committal quality is therefore better measured as missing stance and missing verdict than as a high hedge-word count.

### Cited Findings
- Jiang & Hyland (ESP 2025; 145 essays per group): ChatGPT output had **fewer interactional markers (hedges, boosters, attitude markers)**, which made it read as impersonal. Students showed "higher rhetorical engagement, employing nuanced stance markers and personalised expressions." — [UEA eprint 99123](https://ueaeprints.uea.ac.uk/id/eprint/99123)
- Jiang & Hyland (Written Communication 2025): student essays are "significantly richer in the quantity and variety of engagement features." ChatGPT used fewer questions and personal asides. — [UEA eprint 97952](https://ueaeprints.uea.ac.uk/97952/)
- "Taking a stance" (2026): AI texts had significantly fewer stance expressions, a narrower lexical repertoire, and markedly weaker authorial presence. — reported via [todoele.net listing](https://todoele.net/node/445686) (aggregator; check against the journal)
- Herbold et al.: ChatGPT essays have fewer **epistemic markers**. — [arXiv 2304.14276](https://arxiv.org/abs/2304.14276v1)
- Bharadwaj et al.: "Flattery" (excessive agreement with the user) and "Fog" (vague, non-specific claims) are reward-model biases that diverge from human preferences. — [arXiv 2506.05339](https://arxiv.org/html/2506.05339v2)
- Sharma et al., "Towards Understanding Sycophancy in Language Models" (Anthropic, 2023): RLHF-trained assistants consistently show sycophancy across tasks, and humans and preference models sometimes prefer sycophantic responses over correct ones. — [arXiv 2310.13548](https://arxiv.org/abs/2310.13548) (from prior knowledge, not re-fetched this session)
- Wikipedia lists hedging disclaimers as "among the most common current signs": "should not be treated as an exact census", "While specific details are limited...". Older models used "it's important to note" frequently. Wikipedia also lists Bias/Subjectivity, where text is too objective when a perspective is needed. — [Wikipedia](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing); Shaib et al. IQ2: [arXiv 2509.19163](https://arxiv.org/html/2509.19163v2)
- Gorrie quotes Gemini on its own style: "optimized through training and alignment to project authority, clarity, and inoffensiveness." — [Dead Language Society](https://www.deadlanguagesociety.com/p/rhetorical-analysis-ai)

Illustrative non-committal close *(illustrative)*: "Ultimately, the choice between PostgreSQL and MongoDB depends on your specific needs and use case. Both have their strengths and weaknesses, and the best option will vary from project to project."

### Inferences
- **Signal: "it depends" verdict.** In the final paragraph or section of a comparison or recommendation document (detect comparison via "vs", "or", "which", "best" in the title), flag lemma patterns such as "depends on (your|the) (specific)? (needs|use case|requirements|goals|situation)", "both have (their)? (strengths|pros) and (weaknesses|cons)", "there is no one-size-fits-all", "ultimately, the (best|right) choice", "it's (important|worth) (to note|noting|considering)". Also flag the absence of a superlative or recommendation verb ("use", "choose", "pick", "recommend", "prefer") with a named object.
- **Signal: balance scaffolding.** Count "On the one hand … on the other hand", "While X, Y", and "However, it's important to …" per section. Compute the share of paragraphs that contain both a positive-evaluation and a contrast-concession marker. High symmetry plus no verdict means both-sidesing.
- **Signal: stance density.** Use Hyland's published metadiscourse lists (hedges, boosters, attitude markers, self-mentions) as lexicons. Compute stance markers per 1,000 words, *and* the share of first-person evaluative statements ("I think", "we recommend", "in my experience"). Per Jiang & Hyland, *low* stance density plus high transition and endophoric density is the LLM profile. This is the inverse of the folk "too many hedges" intuition.
- **Signal: disclaimer residue.** Flag "While specific details are limited", "based on available information", "as of my knowledge cutoff", "I don't have access to", and "should not be treated as".
- **Signal: reader flattery.** Flag second-person praise at the start or end: "Great question", "You're absolutely right", "As a savvy reader", "you've got this", and imperative encouragement closers.

### Gaps
- No found study counts "it depends" verdicts in LLM vs. human comparative writing.
- The Jiang & Hyland numbers come from abstracts; per-category frequencies were not retrieved.

---

## 7. Repetition across a document (same point restated, recycled transitions, same paragraph skeleton)

### Takeaway
Repetition is a named slop code (SQ1, "redundant statements") and one of the Fluff-style biases. Simple compression ratio did not predict the slop verdict, which suggests that *semantic* restatement, not lexical repetition, is what readers notice. clarity already measures sentence overlap and section restatement. The gaps are cross-section restatement of claims (paraphrase), recycled transition inventories, and recurrence of the paragraph skeleton.

### Cited Findings
- Shaib et al. define **Repetition (SQ1)** as overused words or phrases, redundant statements and low lexical variety. Their example is three sentences repeating "success" without adding information. Compression ratio as a repetition metric was **not significant**. — [arXiv 2509.19163](https://arxiv.org/html/2509.19163v2)
- Shaib et al. also define Templatedness (SQ2) to include "repeated transitions". — [same](https://arxiv.org/html/2509.19163v2)
- Long-text generation work measures repetition with both n-gram and *semantic* repetition metrics, and notes models learn short-range statistics but not long-range dependencies. — [arXiv 2105.08963](https://arxiv.org/pdf/2105.08963)
- Some long-form generation work reports degradation into "terminal repetitive loops of high-probability words". — via [review of "On Stable Long-Form Generation"](https://www.themoonlight.io/review/on-stable-long-form-generation-benchmarking-and-mitigating-length-volatility) (secondary)
- Wikipedia notes LLMs overuse the rule of three "to make superficial analyses appear more comprehensive". The same skeleton recurs. — [Wikipedia](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- Jiang & Hyland: ChatGPT relies on transitions and endophoric markers, and with metadiscursive nouns it leans on "simpler constructions and anaphoric references". — [UEA 99123](https://ueaeprints.uea.ac.uk/id/eprint/99123); metadiscursive nouns via [todoele.net](https://todoele.net/node/445676) (aggregator)

### Inferences
- **Signal: claim recurrence across sections.** Extract a "claim key" per sentence as the (subject head lemma, ROOT verb lemma, object or attribute head lemma) triple from the dependency parse. Count triples, or near-duplicates sharing 2 of 3 slots, that appear in two or more non-adjacent sections. This catches paraphrase that n-gram overlap misses. Exclude the introduction and conclusion, which clarity's section-restatement rule already covers.
- **Signal: transition inventory.** Collect sentence-initial discourse markers (PDTB list, as used by Herbold et al.): "Additionally", "Furthermore", "Moreover", "However", "Overall", "Ultimately", "Importantly", "Notably". Compute (a) the share of sentences that open with a marker, (b) type/token ratio of markers, and (c) the max reuse of any one marker. Low type/token with high frequency means recycled transitions.
- **Signal: skeleton recurrence.** Reuse the paragraph shape fingerprint from section 4 and count repeated fingerprints in sequence, e.g. 4 consecutive identical shapes.
- **Signal: keyword overuse at document scale.** Take the top-k content lemmas excluding title terms. Flag a non-topic lemma with document frequency in more than 50% of paragraphs, e.g. "landscape", "ensure", "robust", "seamless", "journey". Kobak et al. documented a list of excess words that spiked in post-2023 PubMed abstracts ("delves", "showcasing", "underscores"). — [Kobak et al., arXiv 2406.07016](https://arxiv.org/abs/2406.07016) (from prior knowledge, not re-fetched this session)

### Gaps
- No found study quantifies cross-section semantic restatement rates in LLM vs. human documents.

---

## 8. Coherence failures (missing vs. excessive connectives, ungrounded "this/these", contradictions)

### Takeaway
The findings conflict, so the signal is shape rather than raw count. Herbold et al. found *fewer* discourse markers in ChatGPT essays, while Jiang & Hyland found ChatGPT strong on transitions. Coh-Metrix work shows ChatGPT high on *referential* (surface) cohesion and low on *deep* (causal or intentional) cohesion. The LLM pattern is surface glue ("Additionally", "Furthermore", restated nouns) with weak causal and logical linkage. Copy-editors flag Coherence (SQ3), but deterministic coherence metrics are immature.

### Cited Findings
- Zhou et al. (Coh-Metrix): ChatGPT beat Chinese EFL learners on **referential cohesion** and lost on **deep cohesion**. Revision prompts simplified syntax but deep cohesion still trailed. Narrative genre, early 2023 model. — [arXiv 2303.11812](https://arxiv.org/abs/2303.11812)
- Ismail (2023, Coh-Metrix 3.0, Egyptian university students vs ChatGPT): found ChatGPT essays human-like in cohesion and coherence. This conflicts with Zhou. — [CDELT Occasional Papers](https://journals.ekb.eg/article_325331.html)
- Herbold et al.: ChatGPT text has **fewer discourse markers** (PDTB list), which they use as a coherence measure. ChatGPT-4 outperforms 3.5 on "logical structure… and text linking". — [arXiv 2304.14276](https://arxiv.org/abs/2304.14276v1)
- Jiang & Hyland: ChatGPT's strength is interactive metadiscourse (transitions, endophorics). It uses anaphoric metadiscursive nouns more often, while students use evaluative and evidential nouns. — [UEA 99123](https://ueaeprints.uea.ac.uk/id/eprint/99123); [todoele.net](https://todoele.net/node/445676)
- Shaib et al. define **Coherence (SQ3)** as poor organization, inconsistent argument and hard-to-follow text, with an example of unrelated sentences placed next to each other. In news, it was a significant slop predictor, and no reliable automatic metric was found. — [arXiv 2509.19163](https://arxiv.org/html/2509.19163v2)
- Deng et al.: LMs struggle to maintain long-range structure, including coreference. — [arXiv 2210.08444](https://arxiv.org/pdf/2210.08444)
- Wikipedia: "vague connections" ("in connection with", "associated with") replace direct factual relations. — [Wikipedia](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)

Illustrative ungrounded reference *(illustrative)*: "Microservices can be deployed independently, scaled per service, and written in different languages. **This** makes them a powerful choice for modern teams." Which of the three does "This" refer to? The bare demonstrative points back at a whole list.

### Inferences
- **Signal: additive vs. causal connective ratio.** Classify sentence-initial and medial connectives into additive {additionally, furthermore, moreover, also, in addition}, contrastive {however, but, yet, although}, causal {because, so, therefore, thus, since, as a result, consequently} and temporal. A high additive share with a low causal share is the "surface glue, shallow logic" profile that fits Zhou's deep-cohesion finding. Flag sentences starting with an additive connective whose content-lemma overlap with the previous sentence is near zero. That is a connective without a relation.
- **Signal: bare demonstratives.** Count sentence-initial "This/These/That/Those" tagged as a pronoun (spaCy `PRON` or `DET` with no noun head, dep `nsubj`) rather than a determiner with a noun ("This approach"). Report per 1,000 words, and especially when the previous sentence contains a list or coordination of 3 or more items.
- **Signal: dangling anaphoric summary nouns.** Flag "this approach/issue/process/aspect/factor" where the head noun lemma has not appeared in the previous 2 sentences. Jiang & Hyland report heavier anaphoric metadiscursive noun use by ChatGPT.
- **Signal: contradiction candidates.** This is cheap and only partial. Find pairs of sentences in different sections that share a (subject, verb) claim key but differ in polarity (`neg` child present or absent) or in numeric value for the same entity. Flag them for review, not as errors.
- **Signal: number consistency.** Extract (entity, number, unit) tuples. Flag the same entity with different numbers across the document.

### Gaps
- Evidence on connective frequency conflicts (Herbold: fewer; Jiang & Hyland: strong transitions), and the two used different taxonomies. No study found counts bare "this" in LLM vs. human text.
- Contradiction detection beyond polarity and number heuristics needs NLI models, which fall outside a deterministic spaCy linter.

---

## 9. What teachers, editors and journalists identify as structural giveaways

### Takeaway
Practitioners agree on a short list: tidy five-paragraph or rigid outline structure; polished but generic, example-free content; significance and legacy endings; bold lead-in bullets, title-case headings and over-formatting; explicit antithesis, tricolons and compulsive parallelism; chatbot preambles and closers; and missing personal stance. They also stress that none of these is proof, that detectors produce false positives (notably on non-native writers), and that scrubbing surface tells does not fix the hollowness underneath.

### Cited Findings
- Wikipedia's guide is descriptive, not prescriptive. It says no single sign suffices and that "fixing surface patterns alone can make detection harder" while underlying issues remain. It warns that "False accusations of AI use can drive away new editors." — [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- Teachers and educators cite the default five-paragraph skeleton, polished-but-shallow content, lack of personal connection, and comparing a suspect essay with the student's earlier work as the best method. Anecdotal, often from vendor blogs. — [techlearning](https://www.techlearning.com/how-to/6-ways-teachers-can-tell-students-are-using-ai); [Gizmodo professor interview](https://gizmodo.com/the-biggest-signs-that-ai-wrote-a-paper-according-to-a-professor-2000634580); [Pangram blog](https://pangram.com/blog/how-can-teachers-tell-if-something-is-ai-generated) (vendor)
- Seven detectors flagged non-native English speakers' essays as AI-generated at rates up to 61%. This was reported in secondary educator sources and originates from Liang et al. 2023 ("GPT detectors are biased against non-native English writers"). — via [popularai.org](https://www.popularai.org/p/how-teachers-spot-chatgpt-essays-without-a-detector) (secondary)
- Gorrie traces the tells (antithesis, tricolon, parallelism) to classical rhetoric. The problem is robotic consistency and missing "taste", not the devices themselves. — [Dead Language Society](https://www.deadlanguagesociety.com/p/rhetorical-analysis-ai)
- One tropes directory calls "It's not X, it's Y" the single most commonly identified tell. Commentary. — [tropes.fyi](https://tropes.fyi/directory)
- Critics argue that tells are symptoms and that hollow ideas are the disease. One post notes that a model told to avoid the Wikipedia tells "still doesn't have anything it wants to tell you." Commentary. — [Carly Substack](https://carly.substack.com/p/spotting-machine-made-prose); [putanumonit](https://putanumonit.com/2026/05/28/hw-02-slop-readers/)
- Sam Kriss's essay on why AI writes the way it does was reposted by Longreads in December 2025. It was not fetched, so its claims are not summarized here. — [Longreads via scour.ing](https://scour.ing/@user/p/https://longreads.com/2025/12/04/why-does-a-i-write-like-that)

### Inferences
- The practitioner list maps well onto countable signals in sections 1–8. The hardest item, "nothing to say", is best approximated by combining specificity density (section 2), novelty rate (already in clarity), stance density (section 6) and claim recurrence (section 7) into one document "substance" score, rather than any single rule.
- Given the false-positive literature, clarity rules should be framed as *writing quality* findings with locations and fixes, not as AI-authorship verdicts.

### Gaps
- Practitioner sources rarely quantify. I found no survey of editors that ranks structural tells by frequency.
- The Washington Post figure (~6% of messages containing "not just X, but Y") and the Sam Kriss essay were not verified at source.
