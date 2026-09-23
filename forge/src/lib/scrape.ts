// Forge — reading a page and lifting only what it can prove.
//
// Two rules make this defensible:
//   1. A page counts only if it is ABOUT the part: the number sits somewhere
//      that names the page's product (title, heading, URL path, structured
//      data, a spec row), or is repeated in the body. A search engine thinking
//      a page is relevant is not evidence, and neither is a retailer's
//      "0 results for 99610722553" page echoing the query back.
//   2. Facts come from the product itself, not the page around it. Related
//      products, carousels and navigation are removed before anything is read.

import * as cheerio from 'cheerio';
import type { Evidence, EvidenceFields, Fitment } from './types';
import type { SearchHit } from './search';

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

export const FETCH_TIMEOUT_MS = 7_000;

/** Porsche OE numbers: 11 digits, often written with spaces or dots, e.g.
 *  996 107 225 53 / 99610722553 / 999.113.019.90. */
const OE_PATTERN = /\b(\d{3})[\s.\-]?(\d{3})[\s.\-]?(\d{3})[\s.\-]?(\d{2})\b/g;

/** Only look for OE numbers near words that introduce one. */
const OE_CONTEXT = /\b(OE|OEM|O\.E\.|replaces?|supersed\w*|cross[- ]?ref\w*|reference|interchange|part\s*(?:no|number|#)s?|compatible with)\b/gi;

const MODEL_PATTERN =
  /\b(911|912|914|924|928|930|944|959|964|968|981|982|986|987|991|992|993|996|997|Boxster|Cayman|Cayenne|Macan|Panamera|Taycan)\b/gi;

/** Blocks on a product page that describe OTHER products. */
const NOISE_BLOCK =
  /(^|[-_\s])(related|recommend\w*|also|upsell|cross-?sell|carousel|recent\w*|similar|breadcrumbs?|newsletter|cookie\w*|menu|reviews?)([-_\s]|$)/i;

const SEARCH_URL = /(\/search\b|catalogsearch|[?&](q|keywords?|search_string|query|term|s)=)/i;
const SEARCH_TEXT = /(search results|results for|you searched for|no (products|results|items) (were )?found|returned 0 results|did not match any|0 results)/i;

export function normalisePartNumber(pn: string): string {
  return pn.toUpperCase().replace(/[\s.\-_/]/g, '');
}

/** Loose containment, used for strong locations such as the title or URL. */
export function containsPartNumber(text: string, partNumber: string): boolean {
  const target = normalisePartNumber(partNumber);
  if (target.length < 5) return false; // too short to be a safe match
  return normalisePartNumber(text).includes(target);
}

function countOccurrences(text: string, partNumber: string): number {
  const target = normalisePartNumber(partNumber);
  if (target.length < 5) return 0;
  const hay = normalisePartNumber(text);
  let n = 0;
  for (let i = hay.indexOf(target); i !== -1; i = hay.indexOf(target, i + target.length)) n++;
  return n;
}

/** Two-digit end years take the start year's century, rolling over when the
 *  end is earlier: 1985-89 → 1989, 1997-04 → 2004. */
export function expandEndYear(start: string, end: string): string {
  if (end.length === 4) return end;
  const century = Math.floor(Number(start) / 100) * 100;
  let full = century + Number(end);
  if (full < Number(start)) full += 100;
  return String(full);
}

function extractFitment(text: string): Fitment[] {
  const out: Fitment[] = [];
  const seen = new Set<string>();
  const line =
    /\b(9\d{2}|Boxster|Cayman|Cayenne|Macan|Panamera|911|944|928|924|968|964|993)\b[^.\n;]{0,60}?(\d\.\d)\s*L?[^.\n;]{0,30}?((?:19|20)\d{2})\s*(?:[-–]|to)\s*((?:19|20)?\d{2})?/gi;

  for (const m of text.matchAll(line)) {
    const model = m[1];
    const engine = `${m[2]}L`;
    const from = m[3];
    const years = m[4] ? `${from}-${expandEndYear(from, m[4]).slice(-2)}` : `${from} on`;
    const key = `${model.toLowerCase()}|${engine}|${years}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ model, engine, years });
    if (out.length >= 10) break;
  }

  if (!out.length) {
    const models = new Set<string>();
    for (const m of text.matchAll(MODEL_PATTERN)) models.add(m[1]);
    for (const model of [...models].slice(0, 6)) out.push({ model });
  }
  return out;
}

function extractOeReferences(texts: string[], selfPartNumber: string): string[] {
  const self = normalisePartNumber(selfPartNumber);
  const found = new Set<string>();
  const take = (s: string) => {
    for (const m of s.matchAll(OE_PATTERN)) {
      const joined = `${m[1]}${m[2]}${m[3]}${m[4]}`;
      // Genuine Porsche numeric part numbers start with 9. This also keeps
      // UK phone numbers (0800..., 01494...) out.
      if (joined !== self && joined.startsWith('9')) found.add(joined);
    }
  };
  for (const t of texts) {
    for (const m of t.matchAll(OE_CONTEXT)) take(t.slice(m.index!, m.index! + 160));
  }
  return [...found].slice(0, 12);
}

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
    const defs = $(dl).find('dd');
    $(dl).find('dt').each((i, dt) => {
      const key = $(dt).text().trim().replace(/:$/, '');
      const val = $(defs[i]).text().trim();
      if (key && val && key.length < 40 && val.length < 120) specs[key] = val;
    });
  });
  return specs;
}

function jsonLdIdentifiers($: cheerio.CheerioAPI): string[] {
  const ids: string[] = [];
  $('script[type="application/ld+json"]').each((_, el) => {
    try {
      const walk = (n: unknown): void => {
        if (!n || typeof n !== 'object') return;
        if (Array.isArray(n)) return n.forEach(walk);
        const o = n as Record<string, unknown>;
        for (const k of ['sku', 'mpn', 'productID', 'name', 'gtin13']) if (typeof o[k] === 'string') ids.push(o[k] as string);
        Object.values(o).forEach(walk);
      };
      walk(JSON.parse($(el).text()));
    } catch (err) {
      // Malformed JSON-LD is common and never fatal: fall through to the
      // other identifier locations.
      if (!(err instanceof SyntaxError)) throw err;
    }
  });
  return ids;
}

export function isSearchResultsPage(url: string, title: string, heading: string): boolean {
  let pathAndQuery = url;
  try {
    const u = new URL(url);
    pathAndQuery = u.pathname + u.search;
  } catch (err) {
    if (!(err instanceof TypeError)) throw err;
  }
  return SEARCH_URL.test(pathAndQuery) || SEARCH_TEXT.test(title) || SEARCH_TEXT.test(heading);
}

/** On a retailer's search page, the links to product pages for this exact
 *  part number. Those pages are the evidence; the search page is not. */
export function productLinksFrom(html: string, baseUrl: string, partNumber: string, limit = 2): string[] {
  const $ = cheerio.load(html);
  const out: string[] = [];
  $('a[href]').each((_, a) => {
    if (out.length >= limit) return false;
    const href = $(a).attr('href')!;
    let abs: string;
    try {
      abs = new URL(href, baseUrl).toString();
    } catch (err) {
      if (!(err instanceof TypeError)) throw err;
      return;
    }
    const u = new URL(abs);
    if (!/^https?:$/.test(u.protocol) || SEARCH_URL.test(u.pathname + u.search) || abs === baseUrl) return;
    const decodedPath = decodeURIComponent(u.pathname);
    if (containsPartNumber(decodedPath, partNumber) || containsPartNumber($(a).text(), partNumber)) {
      if (!out.includes(abs)) out.push(abs);
    }
  });
  return out;
}

export async function fetchPage(url: string, timeoutMs = FETCH_TIMEOUT_MS): Promise<{ html: string; finalUrl: string } | null> {
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': UA, Accept: 'text/html,application/xhtml+xml' },
      signal: AbortSignal.timeout(timeoutMs),
      redirect: 'follow',
    });
    if (!res.ok) return null;
    if (!(res.headers.get('content-type') ?? '').includes('html')) return null;
    return { html: await res.text(), finalUrl: res.url || url };
  } catch {
    // A page that will not load, for any reason, is simply not evidence.
    return null;
  }
}

/** Read one product page into evidence. Returns null for search-results pages. */
export function extractEvidence(html: string, url: string, domain: string, partNumber: string, fallbackTitle = ''): Evidence | null {
  const $ = cheerio.load(html);
  const title = $('title').first().text().trim();
  const heading = $('h1').first().text().trim();
  if (isSearchResultsPage(url, title, heading)) return null;

  const canonical = $('link[rel="canonical"]').attr('href') ?? '';
  const ids = jsonLdIdentifiers($);
  const specs = extractSpecTable($);

  $('script, style, noscript, nav, footer, header, aside, form, iframe').remove();
  $('[class], [id]').each((_, el) => {
    const tag = `${$(el).attr('class') ?? ''} ${$(el).attr('id') ?? ''}`;
    if (NOISE_BLOCK.test(tag)) $(el).remove();
  });
  const text = $('body').text().replace(/\s+/g, ' ').trim();
  if (!text) return null;

  let pathOnly = url;
  try {
    pathOnly = decodeURIComponent(new URL(url).pathname);
  } catch (err) {
    if (!(err instanceof TypeError)) throw err;
  }

  const strong = [title, heading, canonical, pathOnly, ...ids, ...Object.values(specs)];
  const confirmed = strong.some((s) => containsPartNumber(s, partNumber)) || countOccurrences(text, partNumber) >= 2;

  const bullets = $('li')
    .map((_, li) => $(li).text().trim())
    .get()
    .filter((t) => t.length > 15 && t.length < 200)
    .slice(0, 8);

  const fields: EvidenceFields = {
    oeReferences: extractOeReferences([text, ...Object.entries(specs).map(([k, v]) => `${k}: ${v}`)], partNumber),
    fitment: extractFitment(`${heading}. ${text}`),
    specs,
    bullets,
  };

  return {
    url,
    domain,
    title: title || fallbackTitle,
    snippet: text.slice(0, 280),
    partNumberConfirmed: confirmed,
    fields,
    fetchedAt: new Date().toISOString(),
    origin: 'live',
  };
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch (err) {
    if (!(err instanceof TypeError)) throw err;
    return '';
  }
}

/** Turn one search hit into evidence. A retailer search page is followed one
 *  hop to the product pages it links to for this part number. */
export async function harvestEvidence(hit: SearchHit, partNumber: string): Promise<Evidence[]> {
  const page = await fetchPage(hit.url);
  if (!page) return [];

  const direct = extractEvidence(page.html, page.finalUrl, hit.domain || domainOf(page.finalUrl), partNumber, hit.title);
  if (direct) return [direct];

  // It was a search-results page. Follow its product links, one hop only.
  const links = productLinksFrom(page.html, page.finalUrl, partNumber);
  const pages = await Promise.all(links.map((l) => fetchPage(l)));
  return pages.flatMap((p, i) => {
    if (!p) return [];
    const e = extractEvidence(p.html, p.finalUrl, domainOf(p.finalUrl) || hit.domain, partNumber);
    return e ? [e] : [];
  });
}
