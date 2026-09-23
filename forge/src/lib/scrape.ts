// Forge — reading a page and lifting only what it can prove.
//
// The rule that makes this demo defensible: a page contributes facts ONLY if
// the part number physically appears in it. A search engine saying a page is
// relevant is not evidence. The part number on the page is.

import * as cheerio from 'cheerio';
import type { Evidence, EvidenceFields, Fitment } from './types';
import type { SearchHit } from './search';

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

/** Porsche OE numbers: 11 digits, often written with spaces or dots.
 *  e.g. 996 107 225 53 / 99610722553 / 999.113.019.90 */
const OE_PATTERN = /\b(\d{3})[\s.\-]?(\d{3})[\s.\-]?(\d{3})[\s.\-]?(\d{2})\b/g;

const MODEL_PATTERN =
  /\b(911|912|914|924|928|930|944|959|964|968|981|982|986|987|991|992|996|997|Boxster|Cayman|Cayenne|Macan|Panamera|Taycan|Carrera|Targa|Turbo|GT2|GT3|GT4)\b/gi;

export function normalisePartNumber(pn: string): string {
  return pn.toUpperCase().replace(/[\s.\-_/]/g, '');
}

/** Does this text genuinely contain the part number, in any of the formats
 *  suppliers write it in? */
export function containsPartNumber(text: string, partNumber: string): boolean {
  const target = normalisePartNumber(partNumber);
  if (target.length < 5) return false; // too short to be a safe match
  const haystack = normalisePartNumber(text);
  return haystack.includes(target);
}

function extractOeReferences(text: string, selfPartNumber: string): string[] {
  const self = normalisePartNumber(selfPartNumber);
  const found = new Set<string>();
  for (const m of text.matchAll(OE_PATTERN)) {
    const joined = `${m[1]}${m[2]}${m[3]}${m[4]}`;
    if (joined !== self) found.add(joined);
  }
  return [...found].slice(0, 12);
}

function extractFitment(text: string): Fitment[] {
  const out: Fitment[] = [];
  const seen = new Set<string>();

  // Looks for "996 3.4L 1997-2001" and the many ways suppliers write it.
  const line = /\b(9\d{2}|Boxster|Cayman|Cayenne|Macan|Panamera|911|944|928|924|968|964|993)\b[^.\n;]{0,60}?(\d\.\d)\s*L?[^.\n;]{0,30}?((?:19|20)\d{2})\s*[-–>]{1,2}\s*((?:19|20)?\d{2})?/gi;

  for (const m of text.matchAll(line)) {
    const model = m[1];
    const engine = m[2] ? `${m[2]}L` : undefined;
    const from = m[3];
    const to = m[4] ? (m[4].length === 2 ? `20${m[4]}` : m[4]) : undefined;
    const years = to ? `${from}-${to}` : `${from} on`;
    const key = `${model}|${engine}|${years}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ model, engine, years });
    if (out.length >= 10) break;
  }

  // Fall back to bare model mentions when no year ranges were written out.
  if (!out.length) {
    const models = new Set<string>();
    for (const m of text.matchAll(MODEL_PATTERN)) models.add(m[1]);
    for (const model of [...models].slice(0, 6)) out.push({ model });
  }

  return out;
}

/** Spec tables are the most reliable thing on a parts page, so read them
 *  before falling back to prose. */
function extractSpecTable($: cheerio.CheerioAPI): Record<string, string> {
  const specs: Record<string, string> = {};

  $('table tr').each((_, row) => {
    const cells = $(row).find('th,td');
    if (cells.length !== 2) return;
    const key = $(cells[0]).text().trim().replace(/:$/, '');
    const val = $(cells[1]).text().trim();
    if (key && val && key.length < 40 && val.length < 120) specs[key] = val;
  });

  $('dl').each((_, dl) => {
    const terms = $(dl).find('dt');
    const defs = $(dl).find('dd');
    terms.each((i, dt) => {
      const key = $(dt).text().trim().replace(/:$/, '');
      const val = $(defs[i]).text().trim();
      if (key && val && key.length < 40 && val.length < 120) specs[key] = val;
    });
  });

  return specs;
}

function pickSpec(specs: Record<string, string>, ...names: string[]): string | undefined {
  for (const [k, v] of Object.entries(specs)) {
    const lk = k.toLowerCase();
    if (names.some((n) => lk.includes(n))) return v;
  }
  return undefined;
}

export async function fetchPage(url: string, timeoutMs = 20_000): Promise<string | null> {
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': UA, Accept: 'text/html,application/xhtml+xml' },
      signal: AbortSignal.timeout(timeoutMs),
      redirect: 'follow',
    });
    if (!res.ok) return null;
    const type = res.headers.get('content-type') ?? '';
    if (!type.includes('html')) return null;
    return await res.text();
  } catch {
    // A page that will not load is simply not evidence. Move on.
    return null;
  }
}

/** Turn one search hit into evidence, or into nothing. */
export async function harvestEvidence(hit: SearchHit, partNumber: string): Promise<Evidence | null> {
  const html = await fetchPage(hit.url);
  if (!html) return null;

  const $ = cheerio.load(html);
  $('script, style, noscript, nav, footer, header').remove();

  const text = $('body').text().replace(/\s+/g, ' ').trim();
  if (!text) return null;

  const confirmed = containsPartNumber(text, partNumber);
  const specs = extractSpecTable($);

  const bullets = $('li')
    .map((_, li) => $(li).text().trim())
    .get()
    .filter((t) => t.length > 15 && t.length < 200)
    .slice(0, 8);

  const fields: EvidenceFields = {
    oeReferences: extractOeReferences(text, partNumber),
    fitment: extractFitment(text),
    material: pickSpec(specs, 'material', 'composition'),
    dimensions: pickSpec(specs, 'dimension', 'size', 'diameter', 'length'),
    weight: pickSpec(specs, 'weight', 'mass'),
    position: pickSpec(specs, 'position', 'location', 'axle', 'side'),
    quantityRequired: pickSpec(specs, 'quantity', 'qty', 'required', 'per car'),
    specs,
    bullets,
  };

  return {
    url: hit.url,
    domain: hit.domain,
    title: $('title').first().text().trim() || hit.title,
    snippet: hit.snippet || text.slice(0, 280),
    partNumberConfirmed: confirmed,
    fields,
    fetchedAt: new Date().toISOString(),
    origin: 'live',
  };
}
