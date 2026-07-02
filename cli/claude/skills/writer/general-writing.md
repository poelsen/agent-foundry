# General writing, the always-on core

Read this for every draft, whatever the genre. The genre file layers structure and register on top of what follows.

## Build a voice card from the user's sample

A real sample of the user's own writing is the strongest voice lever there is, stronger than any instruction. When you have 2–5 samples in the target register:

**First, sanity-check the sample.** Is it actually in the register you're about to write (a casual blog sample will not steer a formal complaint)? Does the sample itself read AI-generated, significance inflation, rule-of-three triads, bolded-header lists, "it's worth noting"? If it clashes with the genre or looks machine-written, say so and ask for a better sample or permission to proceed on a plain default. Do not blind-imitate a bad sample; you would just propagate the problem.

**Then extract a voice card** and write to it:

- Typical sentence length and how much it varies.
- Two or three ways the author opens paragraphs.
- Punctuation habits (dashes, parentheticals, semicolons).
- Vocabulary register (plain, technical, formal).
- One or two recurring phrases or tics.

These prompts mirror humanizer's own Voice Calibration step, so the two skills stay consistent; you do not need to open humanizer's file to run them. If no sample exists, do not block. Write in a plain, specific, genre-appropriate default and offer to match a sample next time.

## The fluency dial (for non-native English writers)

The author may write fluent but non-native English. Two different things get confused here, so set the dial deliberately:

- **Fix** what impedes the reader: a wrong preposition that changes the meaning, subject–verb disagreement, a genuinely garbled sentence. Correct these in any register.
- **Preserve** what is merely non-native but clear: an unusual-but-correct phrasing, a word a native speaker wouldn't pick that still reads fine. This is the author's voice. Leave it.

Default when unspecified: fix what impedes, preserve the rest. If the user says "clean up my English," ask which they mean before you sand the voice flat, or before you leave a real error standing.

## Rhythm, the highest-leverage readability move

Uniform sentence length is the most reliable machine tell, and it is a global property of the draft that a find-and-replace editor cannot fix. So you own it while drafting:

- Vary sentence length on purpose. Follow a thirty-word sentence with a five-word one. A short sentence after a long one lands like a full stop slammed down.
- Vary sentence openings. Don't start three sentences running with the same structure.
- Read the draft aloud in your head. Wherever you stumble or run out of breath, the sentence is mis-built.
- The tell compounds over length, so variance matters *more* in a long piece, not less. Draft long documents section by section rather than in one monolithic pass.

## Specificity, and the hard line on fabrication

Concrete particulars, real numbers, names, dates, objects, are the strongest signal a person wrote something, and they starve most AI tells at the source. Prefer the specific to the general every time.

But specificity you don't have is not yours to invent. If a draft needs a figure, a name, or a date you weren't given, **ask**. A fabricated-but-plausible detail is a worse failure than a visible gap, especially in financial, scientific, legal, or application writing. Treat every number and named entity as load-bearing: never round or paraphrase a figure the user gave you (`$391.04B` stays `$391.04B`, not `$391B`).

## Cohesion, why good prose flows without connective filler

Flow comes from information order, not from "Furthermore" and "Moreover." Open each sentence with something the previous one already established, and end it on the new or emphatic point. Keep one topic string running down a paragraph. Put the word you most want to land, the number, the verdict, at the end of the sentence, where it carries the most weight.

## Stance, not servility

Commit to a view and defend it. Drop the sycophancy ("Great question," "You're absolutely right") and the reflexive hedging ("it could potentially be argued that it may perhaps"). Opinions framed as opinions read as human; assertions dressed as neutral fact read as machine. "I don't think the price reflects the risk" beats "It is clear that the price is wrong."

## Locale, write for the right side of the Atlantic

Default to British / EU conventions for this author, and switch to US only when the audience is US:

- Spelling: British `-ise`, `colour`, `centre` by default.
- Dates: `6 July 2026`, not `July 6`.
- Vocabulary: `CV` not `résumé`, `whilst` acceptable, `autumn` not `fall`.
- Salutation punctuation differs by locale, see `formal-letter.md`.
- Always write money with an explicit currency code (DKK, EUR, GBP); the audience may be cross-border.

One collision to flag at hand-off: humanizer forces straight quotes, but formal EU-published text uses typographic (curly) quotes. For EU-register documents, tell humanizer the quote style is intentional.

## Per-genre defaults (so the skill works zero-question)

If the user doesn't specify, use these and proceed:

- **Formality:** complaint and formal letter → formal; blog → conversational; email → match the thread or neutral; application → warm-professional; personal letter → casual.
- **Length:** blog ~1000–2000 words (soft); email short; letters one page; complaint one page.
- **Audience/locale:** British/EU unless a US recipient is likely.
- **English variant:** en-GB.
- **Voice sample:** none, but worth asking for once.

## If humanizer is unavailable (fallback only)

The pipeline's step 6 should invoke `Skill(humanizer)`. If that skill is not installed in the current project, do a minimal inline pass instead and warn the user that humanizer is not installed:

- Cut the obvious tells: "it's worth noting," "in today's world," "in conclusion," rule-of-three triads, marketing adjectives (powerful, robust, seamless, cutting-edge), superficial `-ing` analysis ("leveraging," "driving outcomes").
- Re-check sentence-length variation and that every number is intact.
- Replace elaborate constructions with plain `is`/`are`/`has`.

This is a stopgap, not a substitute. Humanizer's full pattern audit is the real thing.
