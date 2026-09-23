// Forge — deciding what we actually know.
//
// The demo's claim is "verify accuracy". Here that means:
//   • only pages that carry the part number count (partNumberConfirmed);
//   • only independent companies count, so one registrable domain = one vote;
//   • a fact seen on two or more sources is corroborated, on one it is
//     single-source (usable, flagged), and when sources disagree the fact is
//     dropped, never averaged or picked.
//
// verify() is the ONLY place facts are accepted. It returns `accepted`, and
// the writer's prompt is built from that and nothing else.

import type {
  AcceptedFact,
  AcceptedFacts,
  AcceptedFitment,
  AcceptedReference,
  Evidence,
  FactConfidence,
  Verification,
  VerificationVerdict,
} from './types';
import { isAuthorised, isBlocked, registrableDomain, dealerName } from './sources';

// ── Normalisation ────────────────────────────────────────────────────

export { registrableDomain } from './sources';

/** Loose equality for supplier-written values. "1.2 kg" = "1,2 kg" = "1.2kg",
 *  "1,200 g" = "1200 g", but "12 kg" != "1,2 kg". */
export function sameValue(a: string, b: string): boolean {
  const norm = (s: string) =>
    s
      .toLowerCase()
      .replace(/(\d),(\d{3})(?!\d)/g, '$1$2') // thousands separator
      .replace(/(\d),(\d)/g, '$1.$2') // decimal comma
      .replace(/\s+/g, '');
  return norm(a) === norm(b);
}

/** Maps a supplier's spec label onto one key, so "Material", "Composition"
 *  and the scraped `material` field are compared as the same fact. */
export function canonicalKey(label: string): string {
  const k = label.toLowerCase().replace(/[:*]+$/, '').replace(/\s+/g, ' ').trim();
  if (/\b(material|composition)\b/.test(k)) return 'material';
  if (/\b(weight|mass)\b/.test(k)) return 'weight';
  if (/\b(qty|quantity|required|per car|per vehicle)\b/.test(k)) return 'quantity required';
  if (/\b(position|location|side|axle)\b/.test(k)) return 'position';
  if (/^(dimensions?|size)$/.test(k)) return 'dimensions';
  return k;
}

/** Spec rows that describe the retailer's offer, not the part. */
const NOT_A_PART_FACT = /\b(price|stock|availability|delivery|dispatch|shipping|sku|ean|barcode|condition|warranty|guarantee|returns?|rating|reviews?)\b/i;

const SCALAR_LABELS: Record<string, string> = {
  material: 'Material',
  dimensions: 'Dimensions',
  weight: 'Weight',
  position: 'Position',
  quantityRequired: 'Quantity required',
};

function normModel(model: string): string {
  return model.toLowerCase().replace(/^porsche\s+/, '').replace(/\s+/g, ' ').trim();
}

/** "1985-1989" → "1985-89", "1997–2004" → "1997-04". Single years unchanged. */
export function normYears(years: string): string {
  const m = years.match(/^\s*((?:19|20)\d{2})\s*[-–]\s*((?:19|20)?\d{2})\s*$/);
  if (!m) return years.trim();
  return `${m[1]}-${m[2].slice(-2)}`;
}

// ── Evidence selection ───────────────────────────────────────────────

/** One vote per company. When a company appears twice, keep the page that
 *  actually carries the part number. */
function independentSources(evidence: Evidence[]): Array<Evidence & { company: string }> {
  const byCompany = new Map<string, Evidence>();
  for (const e of evidence) {
    if (isBlocked(e.domain)) continue; // eBay and friends never count
    const company = registrableDomain(e.domain);
    const prev = byCompany.get(company);
    if (!prev || (!prev.partNumberConfirmed && e.partNumberConfirmed)) byCompany.set(company, e);
  }
  return [...byCompany.entries()].map(([company, e]) => ({ ...e, company }));
}

/** Every attribute one source states, scalar fields and spec rows together,
 *  one value per canonical key. */
function attributesOf(e: Evidence): Map<string, { label: string; value: string }> {
  const out = new Map<string, { label: string; value: string }>();
  for (const [label, value] of Object.entries(e.fields.specs ?? {})) {
    if (!value || NOT_A_PART_FACT.test(label)) continue;
    const key = canonicalKey(label);
    if (!out.has(key)) out.set(key, { label: label.replace(/[:*]+$/, '').trim(), value: value.trim() });
  }
  for (const [field, label] of Object.entries(SCALAR_LABELS)) {
    const value = e.fields[field as keyof typeof SCALAR_LABELS & keyof Evidence['fields']] as string | undefined;
    const key = canonicalKey(label);
    if (value && !out.has(key)) out.set(key, { label, value: value.trim() });
  }
  return out;
}

const conf = (n: number): FactConfidence => (n > 1 ? 'corroborated' : 'single-source');
const anyAuthorised = (companies: Iterable<string>) => [...companies].some(isAuthorised);
const label = (company: string) => dealerName(company) ?? company;

/** When sources disagree: if the authorised dealers among them all say the
 *  same thing, that value stands. Otherwise there is no winner. */
function dealerVerdict<T extends { value: string; domain: string }>(
  distinct: T[],
  all: T[],
  same: (a: string, b: string) => boolean
): string | undefined {
  const dealerValues = all.filter((v) => isAuthorised(v.domain));
  if (!dealerValues.length) return undefined;
  const agreed = dealerValues.every((v) => same(v.value, dealerValues[0].value));
  return agreed && distinct.length > 1 ? dealerValues[0].value : undefined;
}

// ── verify ───────────────────────────────────────────────────────────

export function verify(evidence: Evidence[], partNumber: string): Verification {
  const notes: string[] = [];
  const all = independentSources(evidence);
  const confirming = all.filter((e) => e.partNumberConfirmed);
  const sourcesChecked = all.length;
  const sourcesConfirming = confirming.length;
  const conflicts: Verification['conflicts'] = [];
  const overrides: Verification['overrides'] = [];
  const accepted: AcceptedFacts = { attributes: [], fitment: [], oeReferences: [] };

  if (!sourcesChecked) {
    return {
      verdict: 'unconfirmed', confidence: 0, sourcesChecked: 0, sourcesConfirming: 0,
      corroborated: [], singleSource: [], conflicts: [], overrides: [], accepted,
      notes: [`No page could be retrieved for ${partNumber}.`],
    };
  }
  if (!sourcesConfirming) {
    notes.push(`${sourcesChecked} page(s) retrieved, but none contained the part number ${partNumber}. Treating all extracted facts as unconfirmed.`);
  }

  // Attributes: scalars and spec rows in one namespace.
  const attr = new Map<string, { label: string; values: Array<{ value: string; domain: string }> }>();
  for (const e of confirming) {
    for (const [key, { label, value }] of attributesOf(e)) {
      const entry = attr.get(key) ?? { label, values: [] };
      entry.values.push({ value, domain: e.company });
      attr.set(key, entry);
    }
  }
  for (const { label: name, values } of attr.values()) {
    const distinct: typeof values = [];
    for (const v of values) if (!distinct.some((d) => sameValue(d.value, v.value))) distinct.push(v);
    let chosen = values[0].value;
    if (distinct.length > 1) {
      const dealerValue = dealerVerdict(distinct, values, sameValue);
      if (dealerValue === undefined) {
        conflicts.push({ field: name, kind: 'attribute', values: distinct });
        notes.push(`${name}: ${distinct.length} sources disagree. Left out of the copy.`);
        continue;
      }
      chosen = dealerValue;
      const kept = values.filter((v) => sameValue(v.value, dealerValue));
      const overruled = values.filter((v) => !sameValue(v.value, dealerValue));
      overrides.push({ field: name, kind: 'attribute', kept: { value: dealerValue, domains: kept.map((v) => v.domain) }, overruled });
      notes.push(`${name}: authorised dealer value "${dealerValue}" kept over ${overruled.map((o) => `"${o.value}" (${o.domain})`).join(', ')}.`);
    }
    const backing = values.filter((v) => sameValue(v.value, chosen)).map((v) => v.domain);
    accepted.attributes.push({ label: name, value: chosen, confidence: conf(backing.length), sources: backing, authorised: anyAuthorised(backing) });
  }

  // Fitment: agree per model, then per attribute of that model. A
  // corroborated vehicle carries only corroborated detail; a single-source
  // vehicle carries what its one source said. Disagreeing detail is dropped.
  type Tally = Map<string, Set<string>>;
  const models = new Map<string, { display: string; sources: Set<string>; engine: Tally; years: Tally }>();
  for (const e of confirming) {
    for (const f of e.fields.fitment ?? []) {
      if (!f.model?.trim()) continue;
      const key = normModel(f.model);
      const m = models.get(key) ?? { display: f.model.trim(), sources: new Set(), engine: new Map(), years: new Map() };
      m.sources.add(e.company);
      const add = (t: Tally, v?: string) => {
        if (!v) return;
        const k = v.toUpperCase().replace(/\s+/g, '');
        if (!t.has(k)) t.set(k, new Set());
        t.get(k)!.add(e.company);
      };
      add(m.engine, f.engine);
      add(m.years, f.years ? normYears(f.years) : undefined);
      models.set(key, m);
    }
  }
  for (const m of models.values()) {
    const corroboratedModel = m.sources.size > 1;
    const pick = (t: Tally, what: string): string | undefined => {
      if (t.size === 0) return undefined;
      const entries = [...t.entries()];
      if (t.size > 1) {
        const dealerBacked = entries.filter(([, ds]) => anyAuthorised(ds));
        if (dealerBacked.length === 1) {
          const [value, ds] = dealerBacked[0];
          overrides.push({
            field: `${m.display} ${what}`,
            kind: 'fitment-detail',
            kept: { value, domains: [...ds] },
            overruled: entries.filter(([v]) => v !== value).map(([v, d]) => ({ value: v, domain: [...d].join(', ') })),
          });
          return value;
        }
        conflicts.push({
          field: `${m.display} ${what}`,
          kind: 'fitment-detail',
          values: entries.map(([value, ds]) => ({ value, domain: [...ds].join(', ') })),
        });
        return undefined;
      }
      const [[value, ds]] = entries;
      // A corroborated vehicle carries only corroborated detail, unless an
      // authorised dealer is the one stating it.
      if (corroboratedModel && ds.size < 2 && !anyAuthorised(ds)) return undefined;
      return value;
    };
    const engine = pick(m.engine, 'engine');
    const years = pick(m.years, 'years');
    const vehicle = [m.display, engine, years].filter(Boolean).join(' ');
    accepted.fitment.push({ vehicle, confidence: conf(m.sources.size), sources: [...m.sources], authorised: anyAuthorised(m.sources) });
  }

  // OE references, each with its own confidence.
  const self = partNumber.toUpperCase().replace(/[\s.\-_/]/g, '');
  const refs = new Map<string, Set<string>>();
  for (const e of confirming) {
    for (const r of e.fields.oeReferences ?? []) {
      const ref = r.toUpperCase().replace(/[\s.\-_/]/g, '');
      if (!ref || ref === self) continue;
      if (!refs.has(ref)) refs.set(ref, new Set());
      refs.get(ref)!.add(e.company);
    }
  }
  for (const [ref, ds] of refs) accepted.oeReferences.push({ ref, confidence: conf(ds.size), sources: [...ds], authorised: anyAuthorised(ds) });

  // Human-readable lists for the UI, derived from `accepted` so the two can
  // never disagree.
  const tag = (f: { confidence: FactConfidence; sources: string[] }, s: string) =>
    f.confidence === 'corroborated' ? s : `${s} (${label(f.sources[0])})`;
  const facts: Array<{ confidence: FactConfidence; text: string }> = [
    ...accepted.attributes.map((a) => ({ confidence: a.confidence, text: tag(a, `${a.label}=${a.value}`) })),
    ...accepted.fitment.map((f) => ({ confidence: f.confidence, text: tag(f, `fitment=${f.vehicle}`) })),
    ...accepted.oeReferences.map((r) => ({ confidence: r.confidence, text: tag(r, `oeReference=${r.ref}`) })),
  ];
  const corroborated = facts.filter((f) => f.confidence === 'corroborated').map((f) => f.text);
  const singleSource = facts.filter((f) => f.confidence === 'single-source').map((f) => f.text);

  // Confidence. One independent source carrying the part number establishes
  // identity. More sources raise it, scaled by how much of what they say
  // actually agrees (only meaningful with more than one source).
  let confidence: number;
  if (sourcesConfirming === 0) confidence = 10;
  else if (sourcesConfirming === 1) confidence = 50;
  else {
    const base = sourcesConfirming >= 3 ? 90 : 70;
    const agreement = facts.length ? corroborated.length / facts.length : 0;
    confidence = Math.round(base * (0.8 + 0.2 * agreement));
  }
  if (sourcesConfirming > 0 && facts.length === 0) {
    confidence = Math.min(confidence, 35);
    notes.push('Part number confirmed, but no structured facts could be extracted.');
  }
  // Priority for authorised dealers: a confirming dealer page lifts confidence.
  const dealerConfirming = confirming.some((e) => isAuthorised(e.company));
  if (dealerConfirming) {
    confidence = Math.min(95, confidence + 10);
    notes.push(`Confirmed by an authorised Porsche dealer: ${[...new Set(confirming.filter((e) => isAuthorised(e.company)).map((e) => label(e.company)))].join(', ')}.`);
  }
  const attributeConflicts = conflicts.filter((c) => c.kind === 'attribute').length;
  const detailConflicts = conflicts.length - attributeConflicts;
  confidence = Math.max(0, confidence - attributeConflicts * 8 - detailConflicts * 3);

  let verdict: VerificationVerdict;
  if (attributeConflicts && sourcesConfirming >= 2) verdict = 'conflicting';
  else if (confidence >= 70 && corroborated.length > 0) verdict = 'verified';
  else if (confidence >= 40) verdict = 'probable';
  else verdict = 'unconfirmed';

  return { verdict, confidence, sourcesChecked, sourcesConfirming, corroborated, singleSource, conflicts, overrides, notes, accepted };
}

// Re-exported for tests and the UI.
export type { AcceptedFact, AcceptedFitment, AcceptedReference };
