// Forge harvester, pure functions.
//
// Everything in this file is deterministic and does no I/O: it takes HTML,
// XML or text that the CLI (scripts/harvest.ts) has already fetched and turns
// it into typed data. That split is deliberate. The machine that built this
// could not reach design911.co.uk, so every selector below is a heuristic that
// is proven only against the synthetic fixtures in harvest-lib.test.ts. When a
// live run disagrees with a fixture, fix the heuristic here and add the real
// page shape as a new fixture.

import * as cheerio from 'cheerio';
import type { DescriptionStatus, Part, QualityTier } from '../src/lib/types';
import type { CorpusSample } from '../src/lib/voice';

// ── Types ────────────────────────────────────────────────────────────

/** Which extraction strategy supplied the description. */
export type Strategy = 'json-ld' | 'microdata' | 'container' | 'og-description' | 'none';

export interface ExtractedProduct {
  url: string;
  /** /parts/<PN>/ bare page, /p/<slug>/ rich page, or anything else. */
  pageType: 'parts' | 'p' | 'other';
  title: string;
  name: string;
  partNumber: string;
  category: string;
  price?: string;
  brand?: string;
  /** Title, name or brand says Original / Genuine Porsche. */
  genuine: boolean;
  /** Sanitised: only p, br, ul, li, strong survive. */
  descriptionHtml: string;
  descriptionText: string;
  shortHtml?: string;
  strategy: Strategy;
  /** True when the description came from og:description only. Meta tags are
   *  often truncated or site-wide, so the text is not trusted as a listing. */
  weak: boolean;
}

export interface DescriptionContext {
  name?: string;
  partNumber?: string;
  title?: string;
}

export interface DescriptionVerdict {
  status: DescriptionStatus;
  /** Characters left once boilerplate sentences are removed. */
  realContentLength: number;
  reason: string;
}

export interface RobotsRules {
  /** Which group was applied: a named agent token, or '*'. */
  agent: string;
  allow: string[];
  disallow: string[];
  crawlDelaySeconds?: number;
  sitemaps: string[];
}

export interface SitemapParse {
  kind: 'index' | 'urlset' | 'unknown';
  locs: string[];
}

export type CandidatePart = Part & { statusNote: string };

// ── Thresholds (documented, tune here) ───────────────────────────────

/** Under this many characters of real (non-boilerplate) text, a description
 *  is "thin": it exists, but a buyer learns almost nothing from it. 120 chars
 *  is roughly one plain sentence, e.g. "Water pump for Porsche 996 3.4L,
 *  supplied with gasket." Every real Design 911 listing seen in search results
 *  runs well past this because the fitment line alone is longer. */
export const THIN_THRESHOLD_CHARS = 120;

/** After stripping the product name, the part number, boilerplate and filler
 *  words, fewer than this many meaningful tokens means the "description" only
 *  restates what the page title already says. That counts as missing. */
export const RESTATEMENT_MIN_TOKENS = 3;

/** Sentences that appear site-wide or say nothing about the part. Any sentence
 *  matching one of these is removed before the text is measured. */
export const BOILERPLATE_PATTERNS: RegExp[] = [
  /dedicated to your porsche needs/i,
  /no (product )?description (is )?(currently )?(available|yet)/i,
  /description (coming soon|to follow|not available)/i,
  /(buy|order|shop) (it )?(online )?(now )?(at|from|with) design ?911/i,
  /^design ?911\b.*(specialist|supplier|established|since)/i,
  /(free|fast|next[- ]day|worldwide) (uk |eu )?(delivery|shipping)/i,
  /we (ship|deliver) worldwide/i,
  /(call|contact) us (on|at|today)/i,
  /click here/i,
  /add to (basket|cart)/i,
  /^(in|out of) stock\.?$/i,
  /please (check|confirm) (your )?(vin|chassis)/i,
  /lorem ipsum/i,
];

// Words that carry no information once the name and part number are removed.
const FILLER = new Set([
  'a', 'an', 'the', 'for', 'and', 'or', 'with', 'this', 'that', 'is', 'it', 'of', 'to', 'in',
  'on', 'part', 'parts', 'porsche', 'genuine', 'original', 'oem', 'number', 'no', 'item',
  'product', 'new', 'design', '911', 'design911', 'uk', 'by',
]);

// ── Small helpers ────────────────────────────────────────────────────

export function collapse(s: string): string {
  return s.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Plain text from an HTML fragment, with block boundaries kept as spaces. */
export function htmlToText(html: string): string {
  if (!html) return '';
  const spaced = html.replace(/<(br|\/p|\/li|\/div|\/h[1-6]|\/tr|\/ul|\/ol)\b[^>]*>/gi, ' $&');
  const $ = cheerio.load(`<div id="__x">${spaced}</div>`);
  $('#__x script, #__x style, #__x noscript').remove();
  return collapse($('#__x').text());
}

/** Porsche and aftermarket part numbers: 9-13 alphanumerics with at least 7
 *  digits. Matches 99761209005, 9A110622502, V04015005BT, 99610632671. */
const PN_TOKEN = /^[A-Z0-9]{9,13}$/;
export function looksLikePartNumber(token: string): boolean {
  const t = token.toUpperCase();
  return PN_TOKEN.test(t) && (t.match(/\d/g)?.length ?? 0) >= 7;
}

export function partNumberFromUrl(url: string): string {
  try {
    const m = new URL(url).pathname.match(/\/parts\/([^/]+)\/?$/i);
    if (!m) return '';
    const pn = decodeURIComponent(m[1]).toUpperCase().replace(/[\s.-]/g, '');
    return looksLikePartNumber(pn) ? pn : '';
  } catch {
    return '';
  }
}

/** Strips the site suffix: "... | Design911", "... | Design 911". */
export function stripSiteSuffix(title: string): string {
  return collapse(title.replace(/\s*[|–-]\s*design\s?911(\.co\.uk|\.com)?\s*$/i, ''));
}

/** Part number from a page title. Prefers the trailing "- <PN>" or
 *  "- <PN>/1" that Design 911 appends, then the first PN-like token. */
export function partNumberFromTitle(title: string): string {
  const t = stripSiteSuffix(title);
  const tail = t.match(/[-–]\s*([A-Z0-9]{9,13})(?:\/\d+)?\s*$/i);
  if (tail && looksLikePartNumber(tail[1])) return tail[1].toUpperCase();
  for (const tok of t.split(/[^A-Za-z0-9]+/)) {
    if (looksLikePartNumber(tok)) return tok.toUpperCase();
  }
  return '';
}

export function normalisePartNumber(raw: string): string {
  const s = collapse(raw).toUpperCase().replace(/\/\d+$/, '');
  const squashed = s.replace(/[\s.-]/g, '');
  return looksLikePartNumber(squashed) ? squashed : s;
}

const GENUINE_RE = /\b(original|genuine)\s+porsche\b/i;

/** Human-usable name from a raw page title or heading. */
export function cleanName(raw: string, partNumber: string): string {
  let s = stripSiteSuffix(raw);
  if (partNumber) s = s.replace(new RegExp(`${partNumber}(\\/\\d+)?`, 'gi'), ' ');
  s = s.replace(/\b(original|genuine)\s+porsche\s+part(s)?\b/gi, ' ');
  s = collapse(s).replace(/^[\s\-–|:]+|[\s\-–|:]+$/g, '');
  if (BOILERPLATE_PATTERNS.some((re) => re.test(s))) s = '';
  return collapse(s);
}

function formatPrice(amount: unknown, currency?: unknown): string | undefined {
  if (amount === undefined || amount === null || amount === '') return undefined;
  const n = Number(String(amount).replace(/[^0-9.]/g, ''));
  if (!Number.isFinite(n) || n <= 0) return undefined;
  const cur = String(currency ?? 'GBP').toUpperCase();
  const sym = cur === 'GBP' ? '£' : cur === 'EUR' ? '€' : cur === 'USD' ? '$' : `${cur} `;
  return `${sym}${n.toFixed(2)}`;
}

// ── Sanitiser ────────────────────────────────────────────────────────

const DROP_ENTIRELY = new Set([
  'script', 'style', 'noscript', 'iframe', 'svg', 'template', 'form', 'button', 'input',
  'select', 'textarea', 'img', 'video', 'audio', 'object', 'embed', 'canvas', 'head', 'link', 'meta',
]);
const BLOCKISH = new Set([
  'div', 'section', 'article', 'header', 'footer', 'aside', 'main', 'blockquote', 'table',
  'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'dl', 'dt', 'dd', 'figure', 'figcaption',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'pre', 'address', 'center',
]);
const HEADINGS = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']);

/** The slice of the parser's DOM node shape the sanitiser needs. Declared
 *  locally so this file depends only on cheerio, not its transitive deps. */
interface DomNode {
  type: string;
  name?: string;
  data?: string;
  children?: DomNode[];
}

function hasBlockChild(el: DomNode): boolean {
  return (el.children ?? []).some((c) => c.type === 'tag' && BLOCKISH.has((c.name ?? '').toLowerCase()));
}

/**
 * Keeps only p, br, ul, li, strong, with no attributes. Everything else is
 * unwrapped (text kept) or, for scripts/media/forms, dropped with its content.
 * Mappings: b → strong, ol → ul, headings → <p><strong>…</strong></p>,
 * a div holding only inline content → p. Empty tags are removed.
 */
export function sanitiseDescriptionHtml(html: string): string {
  if (!html) return '';
  const $ = cheerio.load(`<div id="__root">${html}</div>`);
  const root = $('#__root').get(0) as unknown as DomNode | undefined;
  if (!root) return '';

  const walk = (nodes: DomNode[] | undefined, inBlock: boolean): string => {
    let out = '';
    for (const el of nodes ?? []) {
      if (el.type === 'text') {
        out += escapeHtml((el.data ?? '').replace(/\s+/g, ' '));
        continue;
      }
      if (el.type !== 'tag' && el.type !== 'script' && el.type !== 'style') continue;
      const tag = (el.name ?? '').toLowerCase();
      if (DROP_ENTIRELY.has(tag)) continue;
      if (tag === 'br') { out += '<br>'; continue; }
      if (tag === 'strong' || tag === 'b') { out += `<strong>${walk(el.children, inBlock)}</strong>`; continue; }
      if (tag === 'ul' || tag === 'ol') { out += `<ul>${walk(el.children, true)}</ul>`; continue; }
      if (tag === 'li') { out += `<li>${walk(el.children, true)}</li>`; continue; }
      if (tag === 'p') {
        out += inBlock ? ` ${walk(el.children, true)} ` : `<p>${walk(el.children, true)}</p>`;
        continue;
      }
      if (HEADINGS.has(tag)) {
        const inner = walk(el.children, true);
        out += inBlock ? ` <strong>${inner}</strong> ` : `<p><strong>${inner}</strong></p>`;
        continue;
      }
      if (BLOCKISH.has(tag)) {
        if (!inBlock && !hasBlockChild(el)) out += `<p>${walk(el.children, true)}</p>`;
        else out += ` ${walk(el.children, inBlock)} `;
        continue;
      }
      // Inline element we do not keep (span, a, em, i, font, …): unwrap.
      out += walk(el.children, inBlock);
    }
    return out;
  };

  let out = walk(root.children, false);

  // Loose top-level text or inline runs get wrapped into paragraphs.
  const parts: string[] = [];
  let loose = '';
  const flush = () => {
    if (collapse(loose.replace(/<br>/g, ''))) parts.push(`<p>${loose}</p>`);
    loose = '';
  };
  for (const piece of out.split(/(<p>[\s\S]*?<\/p>|<ul>[\s\S]*?<\/ul>)/)) {
    if (!piece) continue;
    if (piece.startsWith('<p>') || piece.startsWith('<ul>')) { flush(); parts.push(piece); }
    else loose += piece;
  }
  flush();
  out = parts.join('');

  // Tidy whitespace and empties.
  let prev = '';
  while (prev !== out) {
    prev = out;
    out = out
      .replace(/\s+/g, ' ')
      .replace(/\s*(<\/?(p|ul|li)>)\s*/g, '$1')
      .replace(/<(p|li|strong)>(\s|<br>)*<\/\1>/g, '')
      .replace(/<ul><\/ul>/g, '')
      .replace(/<p>(\s|<br>)+/g, '<p>')
      .replace(/(\s|<br>)+<\/p>/g, '</p>')
      .replace(/(<br>\s*){3,}/g, '<br><br>');
  }
  return out.trim();
}

// ── Description classifier ───────────────────────────────────────────

function sentences(text: string): string[] {
  return text.split(/(?<=[.!?])\s+|\s*\n+\s*/).map(collapse).filter(Boolean);
}

/** Removes boilerplate sentences, returns what is left. */
export function stripBoilerplate(text: string): string {
  return collapse(sentences(text).filter((s) => !BOILERPLATE_PATTERNS.some((re) => re.test(s))).join(' '));
}

/**
 * Full verdict with a reason and the measured length.
 *   missing: empty; only boilerplate; or only restates the name / part number
 *            (fewer than RESTATEMENT_MIN_TOKENS meaningful tokens remain once
 *            name, part number, title and filler words are removed).
 *   thin:    real content under THIN_THRESHOLD_CHARS characters.
 *   present: anything else.
 */
export function explainDescription(text: string, ctx: DescriptionContext = {}): DescriptionVerdict {
  const plain = /<[a-z][\s\S]*>/i.test(text) ? htmlToText(text) : collapse(text ?? '');
  if (!plain) return { status: 'missing', realContentLength: 0, reason: 'empty' };

  const real = stripBoilerplate(plain);
  if (!real) return { status: 'missing', realContentLength: 0, reason: 'boilerplate only' };

  const known = new Set<string>();
  for (const src of [ctx.name, ctx.title ? stripSiteSuffix(ctx.title) : undefined]) {
    for (const tok of (src ?? '').toLowerCase().split(/[^a-z0-9]+/)) if (tok) known.add(tok);
  }
  const pn = (ctx.partNumber ?? '').toLowerCase();
  // Any other PN-like token (an OE cross-reference) still counts as real
  // information; only this part's own number is discounted.
  const meaningful = real
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length >= 2 && !FILLER.has(t) && !known.has(t) && t !== pn);
  if (meaningful.length < RESTATEMENT_MIN_TOKENS) {
    return { status: 'missing', realContentLength: real.length, reason: 'only restates the name / part number' };
  }
  if (real.length < THIN_THRESHOLD_CHARS) {
    return { status: 'thin', realContentLength: real.length, reason: `under ${THIN_THRESHOLD_CHARS} chars of real content` };
  }
  return { status: 'present', realContentLength: real.length, reason: 'has real content' };
}

export function classifyDescription(text: string, ctx: DescriptionContext = {}): DescriptionStatus {
  return explainDescription(text, ctx).status;
}

// ── Product extraction ───────────────────────────────────────────────

type Json = Record<string, unknown>;

function asArray<T>(v: T | T[] | undefined | null): T[] {
  return v === undefined || v === null ? [] : Array.isArray(v) ? v : [v];
}

function typeIs(node: Json, t: string): boolean {
  return asArray(node['@type'] as string | string[]).some((x) => String(x).toLowerCase() === t.toLowerCase());
}

/** JSON-LD strings often arrive HTML-entity encoded ("Water &amp; Coolant",
 *  or a description as "&lt;p&gt;…"). Decoded once; a <textarea> parses as
 *  RCDATA, so entities are resolved but no tags are created. */
export function decodeEntities(s: string): string {
  if (!/&(#\d+|#x[0-9a-f]+|[a-z]+);/i.test(s)) return s;
  const $ = cheerio.load(`<textarea>${s.replace(/<\/textarea/gi, '')}</textarea>`);
  return $('textarea').text();
}

function str(v: unknown): string {
  if (v === undefined || v === null) return '';
  if (typeof v === 'string') return collapse(decodeEntities(v));
  if (typeof v === 'number') return String(v);
  if (typeof v === 'object' && 'name' in (v as Json)) return str((v as Json).name);
  return '';
}

/** Parses every JSON-LD block, flattening arrays and @graph. Bad JSON is
 *  skipped, not fatal: CMS templates often emit trailing commas. */
export function readJsonLd($: cheerio.CheerioAPI): Json[] {
  const nodes: Json[] = [];
  $('script[type="application/ld+json"]').each((_, el) => {
    const raw = $(el).text().trim();
    if (!raw) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      try {
        parsed = JSON.parse(raw.replace(/,\s*([}\]])/g, '$1').replace(/[\u0000-\u001f]+/g, ' '));
      } catch {
        return;
      }
    }
    const stack = asArray(parsed as Json | Json[]);
    while (stack.length) {
      const n = stack.shift();
      if (!n || typeof n !== 'object') continue;
      nodes.push(n);
      if (Array.isArray(n['@graph'])) stack.push(...(n['@graph'] as Json[]));
    }
  });
  return nodes;
}

function priceFromOffers(offers: unknown): string | undefined {
  for (const o of asArray(offers as Json | Json[])) {
    if (!o || typeof o !== 'object') continue;
    const p = formatPrice(o.price ?? o.lowPrice, o.priceCurrency);
    if (p) return p;
    const spec = asArray(o.priceSpecification as Json | Json[])[0];
    if (spec) {
      const sp = formatPrice(spec.price, spec.priceCurrency);
      if (sp) return sp;
    }
  }
  return undefined;
}

function lastCategorySegment(cat: string): string {
  const segs = cat.split(/\s*(?:>|\/|»|\|)\s*/).map(collapse).filter(Boolean);
  return segs[segs.length - 1] ?? '';
}

function breadcrumbCategory($: cheerio.CheerioAPI, jsonLd: Json[]): string {
  const crumbList = jsonLd.find((n) => typeIs(n, 'BreadcrumbList'));
  if (crumbList) {
    const items = asArray(crumbList.itemListElement as Json[])
      .slice()
      .sort((a, b) => Number(a.position ?? 0) - Number(b.position ?? 0))
      .map((i) => str(i.name) || str(i.item));
    // Last crumb is usually the product itself; the one before is its category.
    if (items.length >= 2) return items[items.length - 2];
  }
  const crumbs = $(
    '.breadcrumb li, .breadcrumbs li, nav[aria-label*="readcrumb" i] li, [itemtype*="BreadcrumbList"] [itemprop="itemListElement"]'
  )
    .map((_, el) => collapse($(el).text()))
    .get()
    .filter(Boolean);
  if (crumbs.length >= 2) return crumbs[crumbs.length - 2];
  return '';
}

interface DescCandidate {
  strategy: Strategy;
  html: string;
}

/** Common description containers, most specific first. */
export const DESCRIPTION_SELECTORS = [
  '#tab-description',
  '.product-description',
  '[itemprop="description"]',
  '#description',
  '.description',
  '.tab-content',
];

function containerHtml($: cheerio.CheerioAPI, selector: string): string {
  const el = $(selector).not('nav *, footer *, header *').first();
  if (!el.length) return '';
  if (el.is('meta')) return el.attr('content') ?? '';
  if (selector === '.tab-content') {
    const panes = el.children('.tab-pane, [role="tabpanel"]');
    if (panes.length) {
      const desc = panes.filter((_, p) => /desc/i.test(`${$(p).attr('id') ?? ''} ${$(p).attr('aria-labelledby') ?? ''} ${$(p).attr('class') ?? ''}`));
      return (desc.length ? desc.first() : panes.first()).html() ?? '';
    }
  }
  return el.html() ?? '';
}

/**
 * Pulls a product out of one Design 911 page. Fields are merged across
 * sources (JSON-LD > microdata > page chrome), but the description comes from
 * the first strategy, in order, whose text is not 'missing'; a 'present'
 * description beats a 'thin' one from an earlier strategy. og:description is
 * used only when nothing else has content, and is flagged weak.
 */
export function extractProduct(html: string, url: string): ExtractedProduct {
  const $ = cheerio.load(html);
  let pathname = '';
  try { pathname = new URL(url).pathname; } catch { /* relative or bad url */ }
  const pageType: ExtractedProduct['pageType'] = /^\/parts\//i.test(pathname)
    ? 'parts'
    : /^\/p\//i.test(pathname)
      ? 'p'
      : 'other';

  const title = collapse($('title').first().text());
  const jsonLd = readJsonLd($);
  const ld = jsonLd.find((n) => typeIs(n, 'Product')) ?? {};

  // (b) microdata, scoped to the Product itemscope when there is one.
  const scope = $('[itemtype*="schema.org/Product"]').first();
  const md = (prop: string): string => {
    const el = (scope.length ? scope.find(`[itemprop="${prop}"]`) : $(`[itemprop="${prop}"]`)).first();
    if (!el.length) return '';
    return collapse(el.attr('content') ?? el.attr('value') ?? el.text());
  };
  const mdDescEl = (scope.length ? scope.find('[itemprop="description"]') : $([])).first();

  // Part number.
  const partNumber =
    [str(ld.sku), str(ld.mpn), md('sku'), md('mpn'), md('productID')]
      .map(normalisePartNumber)
      .find(looksLikePartNumber) ||
    partNumberFromUrl(url) ||
    partNumberFromTitle(title) ||
    partNumberFromTitle(collapse($('h1').first().text())) ||
    normalisePartNumber(str(ld.sku) || md('sku'));

  // Name.
  const h1 = collapse($('h1').first().text());
  const ogTitle = collapse($('meta[property="og:title"]').attr('content') ?? '');
  const rawName = str(ld.name) || md('name') || h1 || ogTitle || title;
  const genuine = GENUINE_RE.test(`${title} ${rawName} ${h1}`) || /^porsche$/i.test(str(ld.brand));
  const name =
    cleanName(rawName, partNumber) ||
    cleanName(h1, partNumber) ||
    cleanName(title, partNumber) ||
    (partNumber ? `${genuine ? 'Genuine Porsche part' : 'Part'} ${partNumber}` : 'Unnamed part');

  const brand = str(ld.brand) || str(ld.manufacturer) || md('brand') || undefined;

  const category =
    lastCategorySegment(str(ld.category)) || lastCategorySegment(md('category')) || breadcrumbCategory($, jsonLd);

  const price =
    priceFromOffers(ld.offers) ||
    formatPrice(md('price'), md('priceCurrency')) ||
    formatPrice(
      $('meta[property="product:price:amount"]').attr('content'),
      $('meta[property="product:price:currency"]').attr('content')
    );

  // Description candidates, strategy order.
  const cands: DescCandidate[] = [];
  const ldDesc = str(ld.description);
  if (ldDesc) cands.push({ strategy: 'json-ld', html: ldDesc });
  if (mdDescEl.length) {
    cands.push({ strategy: 'microdata', html: mdDescEl.is('meta') ? mdDescEl.attr('content') ?? '' : mdDescEl.html() ?? '' });
  }
  for (const sel of DESCRIPTION_SELECTORS) {
    const h = containerHtml($, sel);
    if (collapse(htmlToText(h))) cands.push({ strategy: 'container', html: h });
  }
  const og = collapse($('meta[property="og:description"]').attr('content') ?? $('meta[name="description"]').attr('content') ?? '');

  const ctx: DescriptionContext = { name, partNumber, title };
  const judged = cands.map((c) => {
    const clean = /<[a-z][\s\S]*>/i.test(c.html) ? sanitiseDescriptionHtml(c.html) : sanitiseDescriptionHtml(`<p>${escapeHtml(c.html)}</p>`);
    return { ...c, clean, status: classifyDescription(htmlToText(clean), ctx) };
  });
  let pick = judged.find((c) => c.status === 'present') ?? judged.find((c) => c.status === 'thin');
  // JSON-LD descriptions are often the same copy flattened to one plain run.
  // If a later present candidate carries the paragraph structure with at
  // least as much text, take it: the writer learns layout from the corpus.
  const blocks = (h: string) => (h.match(/<(p|li)>/g) ?? []).length;
  if (pick?.status === 'present' && blocks(pick.clean) <= 1) {
    const richer = judged.find(
      (c) => c !== pick && c.status === 'present' && blocks(c.clean) >= 2 && htmlToText(c.clean).length >= htmlToText(pick!.clean).length * 0.9
    );
    if (richer) pick = richer;
  }
  let weak = false;
  if (!pick && og && classifyDescription(og, ctx) !== 'missing') {
    pick = { strategy: 'og-description', html: og, clean: `<p>${escapeHtml(og)}</p>`, status: 'thin' };
    weak = true;
  }
  if (!pick && judged.length) pick = judged[0];

  const shortEl = $('.short-description, .product-short-description, [itemprop="disambiguatingDescription"]').first();
  const shortHtml = shortEl.length ? sanitiseDescriptionHtml(shortEl.html() ?? '') || undefined : undefined;

  const descriptionHtml = pick?.clean ?? '';
  return {
    url,
    pageType,
    title,
    name,
    partNumber,
    category,
    price,
    brand,
    genuine,
    descriptionHtml,
    descriptionText: htmlToText(descriptionHtml),
    shortHtml,
    strategy: pick?.strategy ?? 'none',
    weak,
  };
}

// ── Mapping onto Forge's shapes ──────────────────────────────────────

export function toCorpusSample(p: ExtractedProduct): CorpusSample {
  return {
    partNumber: p.partNumber,
    name: p.name,
    category: p.category || 'Uncategorised',
    ...(p.shortHtml ? { shortHtml: p.shortHtml } : {}),
    longHtml: p.descriptionHtml,
    sourceUrl: p.url,
  };
}

export function manufacturerFor(p: Pick<ExtractedProduct, 'brand' | 'genuine'>): string {
  if (p.genuine) return 'Porsche (Genuine)';
  if (p.brand) return /^porsche$/i.test(p.brand) ? 'Porsche (Genuine)' : p.brand;
  return 'Unknown';
}

export function toCandidatePart(
  p: ExtractedProduct,
  opts: { id: string; harvestedAt: string; verdict?: DescriptionVerdict }
): CandidatePart {
  const verdict = opts.verdict ?? explainDescription(p.descriptionText, { name: p.name, partNumber: p.partNumber, title: p.title });
  const qualityTier: QualityTier = p.genuine || /^porsche$/i.test(p.brand ?? '') ? 'Genuine' : 'Unknown';
  let host = 'design911';
  try { host = new URL(p.url).hostname.replace(/^www\./, ''); } catch { /* keep default */ }
  const part: CandidatePart = {
    id: opts.id,
    partNumber: p.partNumber,
    manufacturer: manufacturerFor(p),
    name: p.name,
    category: p.category || 'Uncategorised',
    summary: '',
    qualityTier,
    ...(p.price ? { price: p.price } : {}),
    sourceUrl: p.url,
    descriptionStatus: verdict.status,
    ...(verdict.status === 'thin' && p.descriptionText ? { existingDescription: p.descriptionText } : {}),
    statusNote:
      `Harvested from ${host} on ${opts.harvestedAt}: description ${verdict.status} (${verdict.reason}; ` +
      `strategy ${p.strategy}${p.weak ? ', weak' : ''}). Summary left blank for a human to fill in.`,
  };
  return part;
}

// ── robots.txt ───────────────────────────────────────────────────────

/**
 * RFC 9309 parsing. Groups start with one or more User-agent lines. The group
 * for `agentToken` (case-insensitive substring match) wins; otherwise `*`.
 * No matching group means everything is allowed.
 */
export function parseRobots(txt: string, agentToken = '*'): RobotsRules {
  type Group = { agents: string[]; allow: string[]; disallow: string[]; delay?: number };
  const groups: Group[] = [];
  const sitemaps: string[] = [];
  let cur: Group | null = null;
  let lastWasAgent = false;

  for (const rawLine of (txt ?? '').split(/\r?\n/)) {
    const line = rawLine.replace(/#.*$/, '').trim();
    if (!line) continue;
    const m = line.match(/^([A-Za-z-]+)\s*:\s*(.*)$/);
    if (!m) continue;
    const key = m[1].toLowerCase();
    const val = m[2].trim();
    if (key === 'sitemap') { if (val) sitemaps.push(val); continue; }
    if (key === 'user-agent') {
      if (!cur || !lastWasAgent) { cur = { agents: [], allow: [], disallow: [] }; groups.push(cur); }
      cur.agents.push(val.toLowerCase());
      lastWasAgent = true;
      continue;
    }
    lastWasAgent = false;
    if (!cur) continue;
    if (key === 'allow') { if (val) cur.allow.push(val); }
    else if (key === 'disallow') { if (val) cur.disallow.push(val); }
    else if (key === 'crawl-delay') { const n = Number(val); if (Number.isFinite(n)) cur.delay = n; }
  }

  const token = agentToken.toLowerCase();
  const named = token !== '*' ? groups.filter((g) => g.agents.some((a) => a !== '*' && token.includes(a))) : [];
  const chosen = named.length ? named : groups.filter((g) => g.agents.includes('*'));
  return {
    agent: named.length ? agentToken : '*',
    allow: chosen.flatMap((g) => g.allow),
    disallow: chosen.flatMap((g) => g.disallow),
    crawlDelaySeconds: chosen.map((g) => g.delay).find((d) => d !== undefined),
    sitemaps,
  };
}

function ruleMatches(rule: string, path: string): boolean {
  const anchored = rule.endsWith('$');
  const body = anchored ? rule.slice(0, -1) : rule;
  const re = new RegExp('^' + body.split('*').map((s) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*') + (anchored ? '$' : ''));
  return re.test(path);
}

/** Longest matching rule wins; Allow wins a tie. Path may include a query. */
export function isAllowed(rules: RobotsRules, pathOrUrl: string): boolean {
  let path = pathOrUrl;
  try {
    const u = new URL(pathOrUrl, 'http://x');
    path = u.pathname + u.search;
  } catch { /* use as-is */ }
  let best = { len: -1, allow: true };
  for (const r of rules.disallow) if (ruleMatches(r, path) && r.length > best.len) best = { len: r.length, allow: false };
  for (const r of rules.allow) if (ruleMatches(r, path) && r.length >= best.len) best = { len: r.length, allow: true };
  return best.allow;
}

// ── Links and sitemaps ───────────────────────────────────────────────

export function isProductPath(pathname: string): boolean {
  return /^\/(parts|p)\/[^/]+\/?$/i.test(pathname);
}

function canonical(u: URL): string {
  u.hash = '';
  u.search = '';
  if (!u.pathname.endsWith('/')) u.pathname += '/';
  return u.toString();
}

/** /parts/<PN>/ and /p/<slug>/ links on the same host as baseUrl, absolute,
 *  query and fragment stripped, trailing slash normalised, deduped. */
export function extractProductLinks(html: string, baseUrl: string): string[] {
  const $ = cheerio.load(html);
  const base = new URL(baseUrl);
  const seen = new Set<string>();
  $('a[href]').each((_, el) => {
    const href = $(el).attr('href') ?? '';
    if (!href || /^(javascript|mailto|tel):/i.test(href)) return;
    let u: URL;
    try { u = new URL(href, base); } catch { return; }
    if (u.hostname !== base.hostname) return;
    if (!isProductPath(u.pathname)) return;
    seen.add(canonical(u));
  });
  return [...seen];
}

/** Listing pages worth crawling from a category or brand page: pagination
 *  (rel=next, /N/ suffix, ?page=N) and, optionally, other /porsche/ and /b/
 *  category links. Same host only. */
export function extractListingLinks(
  html: string,
  pageUrl: string,
  opts: { includeCategories?: boolean } = {}
): { pagination: string[]; categories: string[] } {
  const $ = cheerio.load(html);
  const page = new URL(pageUrl);
  const basePath = page.pathname.replace(/\/\d+\/?$/, '/').replace(/\/?$/, '/');
  const pagination = new Set<string>();
  const categories = new Set<string>();
  $('a[href], link[rel="next"]').each((_, el) => {
    const href = $(el).attr('href') ?? '';
    let u: URL;
    try { u = new URL(href, page); } catch { return; }
    if (u.hostname !== page.hostname || isProductPath(u.pathname)) return;
    u.hash = '';
    const rel = ($(el).attr('rel') ?? '').toLowerCase();
    const isPage =
      rel.includes('next') ||
      (u.pathname.startsWith(basePath) && /^\d+\/?$/.test(u.pathname.slice(basePath.length))) ||
      (u.pathname.replace(/\/?$/, '/') === basePath && /[?&]page=\d+/.test(u.search));
    if (isPage) {
      const key = u.toString();
      if (key !== page.toString()) pagination.add(key);
      return;
    }
    const samePage = u.pathname.replace(/\/?$/, '/') === basePath;
    if (opts.includeCategories && !samePage && /^\/(porsche|b)\/.+/i.test(u.pathname)) {
      u.search = '';
      categories.add(u.toString());
    }
  });
  pagination.delete(canonical(new URL(page.toString())));
  return { pagination: [...pagination], categories: [...categories] };
}

/** <sitemapindex> or <urlset>; returns the <loc> values. */
export function parseSitemap(xml: string): SitemapParse {
  const $ = cheerio.load(xml ?? '', { xml: true });
  const kind: SitemapParse['kind'] = $('sitemapindex').length ? 'index' : $('urlset').length ? 'urlset' : 'unknown';
  const sel = kind === 'index' ? 'sitemapindex > sitemap > loc' : 'urlset > url > loc';
  const locs = $(sel).map((_, el) => collapse($(el).text())).get().filter(Boolean);
  return { kind, locs: [...new Set(locs)] };
}

// ── Selection helpers used by the CLI ────────────────────────────────

/** Round-robin across categories so the corpus is not ten water pumps.
 *  /p/ pages come before other page types within each category. */
export function spreadByCategory<T extends { category: string; pageType?: string }>(items: T[], n: number): T[] {
  const buckets = new Map<string, T[]>();
  const ordered = [...items].sort((a, b) => Number(b.pageType === 'p') - Number(a.pageType === 'p'));
  for (const it of ordered) {
    const k = (it.category || 'Uncategorised').toLowerCase();
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k)!.push(it);
  }
  const lists = [...buckets.values()].sort((a, b) => Number(b[0].pageType === 'p') - Number(a[0].pageType === 'p'));
  const out: T[] = [];
  for (let round = 0; out.length < n; round++) {
    let added = false;
    for (const l of lists) {
      if (round < l.length && out.length < n) { out.push(l[round]); added = true; }
    }
    if (!added) break;
  }
  return out;
}

/** p01, p02, … p10, p11 */
export function renumber<T extends { id: string }>(items: T[], prefix = 'p'): T[] {
  const width = Math.max(2, String(items.length).length);
  return items.map((it, i) => ({ ...it, id: `${prefix}${String(i + 1).padStart(width, '0')}` }));
}
