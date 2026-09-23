// Forge — deciding what we actually know.
//
// The demo's claim is "verify accuracy". That has to mean something specific,
// so here it means: a fact earns its place in the copy by appearing in more
// than one independent source. One source is usable but flagged. Two sources
// that disagree means the fact is dropped, not averaged.

import type { Evidence, Verification, VerificationVerdict } from './types';

/** Loose equality for supplier-written values: "1.2 kg" vs "1.2kg" vs "1,2 KG". */
function sameValue(a: string, b: string): boolean {
  const norm = (s: string) => s.toLowerCase().replace(/[\s,]/g, '').replace(/,/g, '.');
  return norm(a) === norm(b);
}

/** Independent means different companies, not different pages. Two results
 *  from the same domain corroborate nothing. */
function independentSources(evidence: Evidence[]): Evidence[] {
  const seen = new Set<string>();
  const out: Evidence[] = [];
  for (const e of evidence) {
    if (seen.has(e.domain)) continue;
    seen.add(e.domain);
    out.push(e);
  }
  return out;
}

const SCALAR_FIELDS = ['material', 'dimensions', 'weight', 'position', 'quantityRequired'] as const;

export function verify(evidence: Evidence[], partNumber: string): Verification {
  const notes: string[] = [];
  const all = independentSources(evidence);
  const confirming = all.filter((e) => e.partNumberConfirmed);

  const sourcesChecked = all.length;
  const sourcesConfirming = confirming.length;

  if (!sourcesChecked) {
    return {
      verdict: 'unconfirmed',
      confidence: 0,
      sourcesChecked: 0,
      sourcesConfirming: 0,
      corroborated: [],
      singleSource: [],
      conflicts: [],
      notes: [`No page could be retrieved for ${partNumber}.`],
    };
  }

  if (!sourcesConfirming) {
    notes.push(
      `${sourcesChecked} page(s) retrieved, but none contained the part number ${partNumber}. Treating all extracted facts as unconfirmed.`
    );
  }

  const corroborated: string[] = [];
  const singleSource: string[] = [];
  const conflicts: Verification['conflicts'] = [];

  // Scalar fields: material, weight, dimensions and friends.
  for (const field of SCALAR_FIELDS) {
    const values = confirming
      .map((e) => ({ value: e.fields[field], domain: e.domain }))
      .filter((v): v is { value: string; domain: string } => Boolean(v.value));

    if (!values.length) continue;

    const distinct: Array<{ value: string; domain: string }> = [];
    for (const v of values) {
      if (!distinct.some((d) => sameValue(d.value, v.value))) distinct.push(v);
    }

    if (distinct.length > 1) {
      conflicts.push({ field, values: distinct });
      notes.push(`${field}: ${distinct.length} sources disagree. Omitted from the copy.`);
    } else if (values.length > 1) {
      corroborated.push(`${field}=${values[0].value}`);
    } else {
      singleSource.push(`${field}=${values[0].value} (${values[0].domain})`);
    }
  }

  // OE references: corroborated when two independent sources list the same one.
  const refCount = new Map<string, Set<string>>();
  for (const e of confirming) {
    for (const ref of e.fields.oeReferences ?? []) {
      if (!refCount.has(ref)) refCount.set(ref, new Set());
      refCount.get(ref)!.add(e.domain);
    }
  }
  for (const [ref, domains] of refCount) {
    if (domains.size > 1) corroborated.push(`oeReference=${ref}`);
    else singleSource.push(`oeReference=${ref} (${[...domains][0]})`);
  }

  // Fitment: corroborated per MODEL, because suppliers describe the same car
  // differently ("944 2.5L" on one site, "944 1985-89" on another). Two
  // independent sites naming the same model is agreement.
  const fitCount = new Map<string, { domains: Set<string>; detail: string }>();
  for (const e of confirming) {
    for (const f of e.fields.fitment ?? []) {
      const model = f.model?.trim();
      if (!model) continue;
      const key = model.toLowerCase();
      const detail = [f.model, f.engine, f.years].filter(Boolean).join(' ');
      const entry = fitCount.get(key) ?? { domains: new Set<string>(), detail };
      entry.domains.add(e.domain);
      if (detail.length > entry.detail.length) entry.detail = detail;
      fitCount.set(key, entry);
    }
  }
  for (const { domains, detail } of fitCount.values()) {
    if (domains.size > 1) corroborated.push(`fitment=${detail}`);
    else singleSource.push(`fitment=${detail} (${[...domains][0]})`);
  }

  // Confidence. One independent source carrying the part number establishes
  // identity: "probable". More sources raise it, scaled by how much of what
  // they say actually agrees. Agreement is only scored when there is more
  // than one source, otherwise a lone source is penalised twice for the same
  // thing.
  let confidence: number;
  const facts = corroborated.length + singleSource.length;
  if (sourcesConfirming === 0) {
    confidence = 10;
  } else if (sourcesConfirming === 1) {
    confidence = 50;
  } else {
    const base = sourcesConfirming >= 3 ? 90 : 70;
    const agreement = facts ? corroborated.length / facts : 0;
    confidence = Math.round(base * (0.8 + 0.2 * agreement));
  }
  if (sourcesConfirming > 0 && facts === 0) {
    confidence = Math.min(confidence, 35);
    notes.push('Part number confirmed, but no structured facts could be extracted.');
  }
  if (conflicts.length) confidence = Math.max(0, confidence - conflicts.length * 8);

  let verdict: VerificationVerdict;
  if (conflicts.length && sourcesConfirming >= 2) verdict = 'conflicting';
  else if (confidence >= 70) verdict = 'verified';
  else if (confidence >= 40) verdict = 'probable';
  else verdict = 'unconfirmed';

  return {
    verdict,
    confidence,
    sourcesChecked,
    sourcesConfirming,
    corroborated,
    singleSource,
    conflicts,
    notes,
  };
}
