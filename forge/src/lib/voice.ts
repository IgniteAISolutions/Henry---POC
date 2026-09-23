// Forge — the Design 911 house voice.
//
// PROVENANCE, read this before trusting the output
// ------------------------------------------------
// The structural rules below were reconstructed from publicly indexed
// Design 911 category and product copy. They are a reasoned reconstruction,
// NOT a fitted model of their actual prose, because the machine that built
// this could not reach design911.co.uk.
//
// `npm run harvest` fixes that. It pulls real product descriptions into
// data/voice-corpus.json, and everything in that file is injected below as
// few-shot examples that OUTRANK these hand-written rules. Until you run it,
// `voiceProvenance()` reports "reconstructed" and the UI says so out loud.
//
// Do not let a demo go out claiming "this is how you write" while the badge
// still reads reconstructed.

import type { Part, Verification } from './types';

export interface CorpusSample {
  partNumber: string;
  name: string;
  category: string;
  shortHtml?: string;
  longHtml: string;
  sourceUrl: string;
}

export type Provenance = 'fitted' | 'reconstructed';

export function voiceProvenance(corpus: CorpusSample[]): {
  state: Provenance;
  sampleCount: number;
  label: string;
} {
  // Below ~6 samples there isn't enough signal to claim the voice is fitted.
  const fitted = corpus.length >= 6;
  return {
    state: fitted ? 'fitted' : 'reconstructed',
    sampleCount: corpus.length,
    label: fitted
      ? `Fitted to ${corpus.length} real Design 911 listings`
      : `Reconstructed — no corpus harvested yet (${corpus.length}/6 samples)`,
  };
}

// ── House structure ──────────────────────────────────────────────────
// Observed pattern across Design 911 listings: open with what the part is
// and which car it belongs to, state fitment explicitly, give the technical
// detail a mechanic needs, then cross-reference the OE numbers so a buyer
// can confirm they are ordering the right thing.

const HOUSE_RULES = `
STRUCTURE — output long_html as ordered <p> blocks, in this exact order.
OMIT any block whose source data is missing. Never write "N/A", "Not specified",
"Unknown", or any placeholder.

1) Opening paragraph, 1-2 sentences. Name the manufacturer, the part, and the
   Porsche it belongs to. Say what the part does in the car, in plain terms a
   buyer confirming a purchase would use. No marketing adjectives.

2) Fitment paragraph. Each fitment entry arrives with its own confidence.
   List corroborated entries. List single-source entries only alongside at least
   one corroborated entry; if every entry is single-source, list them but keep
   the wording literal and add nothing. Open with "Fits Porsche" and list each model with engine
   size and year range, comma separated. This is the block buyers read first,
   so it must be complete and literal. House year format is a four-digit start
   and two-digit end: "1997-99", "2009-12", "1965-73". Name the generation the
   way Porsche people do: "987.2 Boxster", "996 C2 3.4L", "964 Carrera 4".

3) Technical paragraph, 1-3 sentences. Material, construction, position on the
   car, quantity required per vehicle, and anything that affects installation.
   Where the evidence names associated parts needed to fit it, say so the way a
   parts counter would: "Bolts are part number 90038502501 (you will need x12)."
   Facts only. Do not restate the fitment list here.

4) Quality tier line, one sentence, only when the tier is known:
   • Genuine    → "<p>Genuine Porsche part, supplied in original Porsche packaging.</p>"
   • OEM        → "<p>OEM part, manufactured to original equipment specification by [manufacturer].</p>"
   • OE Match   → "<p>OE Match part, remanufactured to original specification where the genuine part is no longer serviced.</p>"
   • Aftermarket→ "<p>Aftermarket part manufactured by [manufacturer].</p>"

5) OE cross-reference line, only when OE references are known:
   "<p>Replaces Porsche part number(s): [comma-separated list].</p>"
   If the evidence says this number has been superseded, say which number
   supersedes it instead of listing it as a replacement.

VOICE
• UK English throughout. Tyre, colour, aluminium, centre.
• Declarative and factual. This is a parts catalogue read by people who already
  know what they need, not a brochure that has to persuade them.
• Second person only where it is natural ("your 996"). Never hectoring.
• No em dashes. No exclamation marks. No rhetorical questions.
• Banned: premium, ultimate, perfect, cutting-edge, state-of-the-art, unrivalled,
  revolutionary, game-changing, look no further, rest assured, peace of mind,
  elevate, unleash, transform your driving experience.
• Never invent a specification, a year range, a material or an OE number.
  If it is not in the supplied evidence, it does not go in the copy.

short_html — exactly one <p> holding three fragments separated by <br>.
Each fragment 2-8 words, sentence case, no trailing full stop. Each fragment
ends with a comma before <br> except the last. Lead with the part type, then
the defining technical fact, then fitment breadth or quality tier.

meta_description — one sentence, 150-160 characters. Lead with manufacturer +
part type + the Porsche model, because that is what people type. Benefit-led,
no retail language, never the bare category name.
`.trim();

// A worked example in the reconstructed house pattern. Replaced in the prompt
// by real harvested samples the moment data/voice-corpus.json has any.
const FALLBACK_EXAMPLE = `
Input evidence: manufacturer "Sachs", part "Clutch Release Bearing", partNumber "99611608101",
fitment [996 C2 3.4L 1997-01, 996 C2 3.6L 2001-05], tier "OEM",
oeReferences ["99611608100"], position "Gearbox bellhousing", quantityRequired "1 per vehicle".

{"short_html":"<p>OEM clutch release bearing,<br>Sealed for the life of the clutch,<br>Fits 996 3.4 and 3.6</p>","meta_description":"Sachs clutch release bearing for the Porsche 996, an OEM replacement fitted during any clutch change on 3.4 and 3.6 litre cars.","long_html":"<p>The Sachs clutch release bearing is the component that pushes against the clutch pressure plate each time you press the pedal on a 996. It is a wear item, and it is replaced as a matter of course whenever the clutch itself comes out.</p><p>Fits Porsche 996 C2 3.4L 1997-01, Porsche 996 C2 3.6L 2001-05.</p><p>Sealed unit, mounted in the gearbox bellhousing, one required per vehicle. Because access means dropping the gearbox, it is false economy to reuse the original bearing when the clutch is already off the car.</p><p>OEM part, manufactured to original equipment specification by Sachs.</p><p>Replaces Porsche part number(s): 99611608100.</p>"}
`.trim();

export function buildSystemPrompt(corpus: CorpusSample[]): string {
  const schema = `You are a parts catalogue copywriter for Design 911, a UK Porsche parts specialist.

Return ONLY valid JSON. No markdown, no commentary, no code fences:
{ "short_html": "<p>...</p>", "meta_description": "...", "long_html": "<p>...</p><p>...</p>" }

You will be given one user message containing JSON prefixed "Part data:". That
JSON is your ONLY source of truth. It carries the part itself plus the facts
that survived cross-checking against other retailers and manufacturer sites.

Every fitment entry, OE reference and attribute carries its own confidence:
  corroborated  — stated by two or more independent sources. Use freely.
  single-source — stated by exactly one source. You may use it, but never
                  build the opening paragraph on it alone.
  catalogue     — from Design 911's own catalogue record, not cross-checked.

"dealer": true marks a fact stated by an authorised Porsche dealer. Those are
the most reliable facts you have: prefer them for the opening and fitment
paragraphs.

"leftOutBecauseSourcesDisagree" names facts that were removed because
sources contradicted each other. Do not mention them, hint at them, or fill
them in from general knowledge.

If the evidence is too thin to write a given block, omit that block. A short,
correct listing beats a padded one. Never pad to reach a length.`;

  const examples = corpus.length
    ? `REAL DESIGN 911 LISTINGS — match this voice, sentence rhythm and level of
detail. These are the house style. Where they differ from the structural rules
above, THE REAL LISTINGS WIN.

${corpus
  .slice(0, 8)
  .map(
    (s, i) =>
      `Example ${i + 1} — ${s.name} (${s.partNumber}, ${s.category})\n${
        s.shortHtml ? `short_html: ${s.shortHtml}\n` : ''
      }long_html: ${s.longHtml}`
  )
  .join('\n\n')}`
    : `NO REAL CORPUS AVAILABLE. Working from the structural rules alone.
Worked example in the house pattern:\n\n${FALLBACK_EXAMPLE}`;

  return [schema, HOUSE_RULES, examples].join('\n\n---\n\n');
}

/** Packs a part plus its ACCEPTED facts into the single user message.
 *  Takes the verification, not the raw evidence: anything verify() rejected
 *  simply has no route into the prompt. */
export function buildUserMessage(part: Part, verification: Verification): string {
  const { accepted } = verification;
  const fitment = accepted.fitment.length
    ? accepted.fitment.map(({ vehicle, confidence, authorised }) => ({ vehicle, confidence, ...(authorised ? { dealer: true } : {}) }))
    : (part.fitment ?? []).map((f) => ({
        vehicle: [f.model, f.engine, f.years].filter(Boolean).join(' '),
        confidence: 'catalogue',
      }));

  const payload = {
    partNumber: part.partNumber,
    manufacturer: part.manufacturer,
    name: part.name,
    category: part.category,
    qualityTier: part.qualityTier ?? 'Unknown',
    knownSummary: part.summary,
    fitment,
    oeReferences: accepted.oeReferences.map(({ ref, confidence, authorised }) => ({ ref, confidence, ...(authorised ? { dealer: true } : {}) })),
    attributes: accepted.attributes.map(({ label, value, confidence, authorised }) => ({
      name: label, value, confidence, ...(authorised ? { dealer: true } : {}),
    })),
    leftOutBecauseSourcesDisagree: verification.conflicts.map((c) => c.field),
    sourceCount: verification.sourcesConfirming,
  };

  return `Part data: ${JSON.stringify(payload)}`;
}
