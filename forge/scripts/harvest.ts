// Forge harvester CLI: `npm run harvest -- [flags]`
//
// Walks design911.co.uk politely and writes two files:
//   data/products.candidates.json  parts whose page has no real description
//   data/voice-corpus.json         real listings the writer copies the voice from
// data/products.json is only replaced when --write-products is passed.
//
// All parsing lives in scripts/harvest-lib.ts (pure, tested). This file is the
// I/O: fetching, pacing, robots.txt, discovery, and writing files.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { gunzipSync } from 'node:zlib';
import type { Part } from '../src/lib/types';
import {
  type CandidatePart,
  type ExtractedProduct,
  type RobotsRules,
  type Strategy,
  explainDescription,
  extractListingLinks,
  extractProduct,
  extractProductLinks,
  isAllowed,
  isProductPath,
  parseRobots,
  parseSitemap,
  renumber,
  spreadByCategory,
  toCandidatePart,
  toCorpusSample,
} from './harvest-lib';

const USAGE = `Usage: npm run harvest -- [options]

  --find-missing N    parts without a real description to collect (default 10)
  --corpus N          described listings to collect for the voice corpus (default 12)
  --base URL          site root (default $DESIGN911_BASE_URL or https://www.design911.co.uk)
  --seed URL          category or brand page to crawl; repeatable; relative paths ok
  --delay MS          pause between requests (default 1000; robots Crawl-delay wins if longer)
  --max-pages N       hard cap on HTTP requests, robots.txt excluded (default 200)
  --write-products    also replace data/products.json with the candidates (ids p01..pNN)
  --out-dir DIR       where to write the JSON files (default ./data)
  -h, --help          show this help`;

const ROBOTS_TOKEN = 'ForgeHarvester';
const USER_AGENT =
  process.env.HARVEST_USER_AGENT ??
  `Mozilla/5.0 (compatible; ${ROBOTS_TOKEN}/0.1; product-description audit for Design 911; Node.js)`;

const DEFAULT_SEEDS = [
  '/b/original/',
  '/b/genuine/387/',
  '/b/oem-brands/',
  '/porsche/996--911--1997-05/water---coolant-pumps/',
  '/porsche/boxster-986-987-981/ignition-coils/',
];

const MAX_SITEMAP_FILES = 12;
const MAX_CONSECUTIVE_FAILURES = 5;
const REQUEST_TIMEOUT_MS = 20_000;

interface Options {
  findMissing: number;
  corpus: number;
  base: string;
  seeds: string[];
  delay: number;
  maxPages: number;
  writeProducts: boolean;
  outDir: string;
}

class UsageError extends Error {}

/** A network failure the user needs to hear about in one plain line. */
class FetchFailure extends Error {
  constructor(public host: string, public detail: string, public pathname: string) {
    super(`${host} ${detail}`);
  }
}

function projectRoot(): string {
  return typeof __dirname !== 'undefined' ? path.resolve(__dirname, '..') : process.cwd();
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    findMissing: 10,
    corpus: 12,
    base: process.env.DESIGN911_BASE_URL || 'https://www.design911.co.uk',
    seeds: [],
    delay: 1000,
    maxPages: 200,
    writeProducts: false,
    outDir: path.join(projectRoot(), 'data'),
  };
  const num = (flag: string, v: string | undefined, min: number): number => {
    const n = Number(v);
    if (v === undefined || !Number.isInteger(n) || n < min) throw new UsageError(`${flag} needs a whole number >= ${min}`);
    return n;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const [flag, inline] = a.includes('=') ? [a.slice(0, a.indexOf('=')), a.slice(a.indexOf('=') + 1)] : [a, undefined];
    const next = () => inline ?? argv[++i];
    switch (flag) {
      case '--find-missing': opts.findMissing = num(flag, next(), 0); break;
      case '--corpus': opts.corpus = num(flag, next(), 0); break;
      case '--base': opts.base = next() ?? ''; break;
      case '--seed': { const s = next(); if (!s) throw new UsageError('--seed needs a URL'); opts.seeds.push(s); break; }
      case '--delay': opts.delay = num(flag, next(), 0); break;
      case '--max-pages': opts.maxPages = num(flag, next(), 1); break;
      case '--write-products': opts.writeProducts = true; break;
      case '--out-dir': opts.outDir = path.resolve(next() ?? ''); break;
      case '-h': case '--help': console.log(USAGE); process.exit(0);
      default: throw new UsageError(`unknown option ${a}`);
    }
  }
  try {
    const u = new URL(opts.base);
    opts.base = `${u.protocol}//${u.host}`;
  } catch {
    throw new UsageError(`--base is not a URL: ${opts.base}`);
  }
  return opts;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ── Polite fetcher ───────────────────────────────────────────────────

interface Fetched {
  url: string;
  status: number;
  statusText: string;
  text: string;
}

const httpStatus = (r: { status: number; statusText: string }) => `HTTP ${r.status}${r.statusText ? ` ${r.statusText}` : ''}`;

class Fetcher {
  requests = 0;
  private lastAt = 0;
  private consecutiveFailures = 0;
  robots: RobotsRules | null = null;

  constructor(private delayMs: number, private maxRequests: number) {}

  get budgetLeft(): number {
    return this.maxRequests - this.requests;
  }

  setDelay(ms: number) {
    this.delayMs = Math.max(this.delayMs, ms);
  }

  allowed(url: string): boolean {
    return !this.robots || isAllowed(this.robots, url);
  }

  /** Returns the response for any HTTP status. Throws FetchFailure only for
   *  network errors, or once too many requests in a row have failed. */
  async get(url: string, opts: { countTowardCap?: boolean } = {}): Promise<Fetched> {
    const counted = opts.countTowardCap !== false;
    if (counted && this.requests >= this.maxRequests) throw new Error('page cap reached');
    const wait = this.lastAt + this.delayMs - Date.now();
    if (this.lastAt && wait > 0) await sleep(wait);
    this.lastAt = Date.now();
    if (counted) this.requests++;

    const u = new URL(url);
    let res: Response;
    try {
      res = await fetch(url, {
        headers: {
          'User-Agent': USER_AGENT,
          Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5',
          'Accept-Language': 'en-GB,en;q=0.9',
        },
        redirect: 'follow',
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (err) {
      throw new FetchFailure(u.host, describeNetworkError(err), u.pathname);
    }
    const buf = Buffer.from(await res.arrayBuffer());
    // Raw .xml.gz sitemaps arrive as gzip bytes (not Content-Encoding).
    const body = buf.length > 2 && buf[0] === 0x1f && buf[1] === 0x8b ? gunzipSync(buf) : buf;
    const text = body.toString('utf8');

    if (res.ok || res.status === 404 || res.status === 410) this.consecutiveFailures = 0;
    else if (++this.consecutiveFailures >= MAX_CONSECUTIVE_FAILURES || res.status === 429) {
      throw new FetchFailure(u.host, `returned ${httpStatus(res)}`, u.pathname);
    }
    return { url: res.url || url, status: res.status, statusText: res.statusText, text };
  }
}

function describeNetworkError(err: unknown): string {
  const e = err as { name?: string; message?: string; cause?: { code?: string; message?: string } };
  if (e?.name === 'TimeoutError' || e?.name === 'AbortError') return `did not respond within ${REQUEST_TIMEOUT_MS / 1000}s`;
  const code = e?.cause?.code;
  if (code === 'ENOTFOUND' || code === 'EAI_AGAIN') return `could not be resolved (DNS ${code})`;
  if (code) return `refused the connection (${code})`;
  return `could not be reached (${e?.cause?.message || e?.message || 'network error'})`;
}

// ── Discovery ────────────────────────────────────────────────────────

/** Round-robin over sources so one long listing page cannot dominate. */
class SpreadQueue {
  private lists = new Map<string, string[]>();
  private order: string[] = [];
  private cursor = 0;

  push(source: string, urls: string[]) {
    if (!urls.length) return;
    if (!this.lists.has(source)) { this.lists.set(source, []); this.order.push(source); }
    this.lists.get(source)!.push(...urls);
  }

  get size(): number {
    let n = 0;
    for (const l of this.lists.values()) n += l.length;
    return n;
  }

  shift(): string | undefined {
    for (let tries = 0; tries < this.order.length; tries++) {
      const key = this.order[this.cursor % this.order.length];
      this.cursor++;
      const l = this.lists.get(key)!;
      if (l.length) return l.shift();
    }
    return undefined;
  }
}

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

async function discoverFromSitemaps(f: Fetcher, opts: Options, want: number): Promise<string[]> {
  const host = new URL(opts.base).hostname;
  const queue = [...new Set([...(f.robots?.sitemaps ?? []), `${opts.base}/sitemap.xml`, `${opts.base}/sitemap_index.xml`])];
  const seen = new Set<string>();
  const found = new Set<string>();
  let files = 0;
  while (queue.length && files < MAX_SITEMAP_FILES && found.size < want && f.budgetLeft > 0) {
    const url = queue.shift()!;
    if (seen.has(url)) continue;
    seen.add(url);
    let u: URL;
    try { u = new URL(url, opts.base); } catch { continue; }
    if (u.hostname !== host || !f.allowed(u.pathname)) continue;
    files++;
    const res = await f.get(u.toString());
    if (res.status !== 200) {
      console.log(`  sitemap ${u.pathname}: HTTP ${res.status}`);
      continue;
    }
    const sm = parseSitemap(res.text);
    console.log(`  sitemap ${u.pathname}: ${sm.kind}, ${sm.locs.length} entries`);
    if (sm.kind === 'index') {
      // Product-looking child sitemaps first.
      const kids = [...sm.locs].sort((a, b) => Number(/product|part|\/p[-_]/i.test(b)) - Number(/product|part|\/p[-_]/i.test(a)));
      queue.unshift(...kids);
    } else {
      for (const loc of sm.locs) {
        try {
          const lu = new URL(loc);
          if (lu.hostname === host && isProductPath(lu.pathname)) {
            lu.hash = ''; lu.search = '';
            if (!lu.pathname.endsWith('/')) lu.pathname += '/';
            found.add(lu.toString());
          }
        } catch { /* skip bad loc */ }
      }
    }
  }
  return [...found];
}

// ── Main ─────────────────────────────────────────────────────────────

interface Stats {
  productPages: number;
  listingPages: number;
  sitemapAndOther: number;
  skippedByRobots: number;
  httpErrors: number;
  noPartNumber: number;
  strategies: Record<Strategy, number>;
  status: { missing: number; thin: number; present: number };
}

async function run(opts: Options): Promise<number> {
  const started = new Date();
  const harvestedAt = started.toISOString().replace(/\.\d+Z$/, 'Z');
  const host = new URL(opts.base).host;
  const f = new Fetcher(opts.delay, opts.maxPages);
  const stats: Stats = {
    productPages: 0, listingPages: 0, sitemapAndOther: 0, skippedByRobots: 0, httpErrors: 0, noPartNumber: 0,
    strategies: { 'json-ld': 0, microdata: 0, container: 0, 'og-description': 0, none: 0 },
    status: { missing: 0, thin: 0, present: 0 },
  };

  let stopping = false;
  process.on('SIGINT', () => {
    if (stopping) process.exit(130);
    stopping = true;
    console.log('\nStopping after this request and writing what was collected (Ctrl-C again to abort).');
  });

  console.log(`Forge harvester: ${opts.base}  (find ${opts.findMissing} missing, corpus ${opts.corpus}, delay ${opts.delay}ms, cap ${opts.maxPages})`);

  // robots.txt. If it cannot be read (other than a plain 404), do not crawl.
  const robotsRes = await f.get(`${opts.base}/robots.txt`, { countTowardCap: false });
  if (robotsRes.status === 200) {
    f.robots = parseRobots(robotsRes.text, ROBOTS_TOKEN);
    if (f.robots.crawlDelaySeconds) f.setDelay(f.robots.crawlDelaySeconds * 1000);
    console.log(`robots.txt: group "${f.robots.agent}", ${f.robots.disallow.length} disallow rules, ${f.robots.sitemaps.length} sitemaps listed`);
  } else if (robotsRes.status === 404 || robotsRes.status === 410) {
    console.log('robots.txt: none published, crawling with no restrictions beyond the page cap');
  } else {
    throw new FetchFailure(host, `returned ${httpStatus(robotsRes)}`, '/robots.txt');
  }

  const partsQ = new SpreadQueue();
  const pQ = new SpreadQueue();
  const seen = new Set<string>();
  const enqueueProducts = (source: string, urls: string[]) => {
    const parts: string[] = [];
    const ps: string[] = [];
    for (const u of urls) {
      if (seen.has(u)) continue;
      seen.add(u);
      (new URL(u).pathname.startsWith('/parts/') ? parts : ps).push(u);
    }
    partsQ.push(source, parts);
    pQ.push(source, ps);
  };

  // Discovery and fetching. A network failure part-way through keeps what
  // was already collected; a failure before any product page aborts cleanly.
  const candidates: Array<{ p: ExtractedProduct; part: CandidatePart }> = [];
  const pool: ExtractedProduct[] = [];
  let aborted: FetchFailure | null = null;
  const categoriesIn = (xs: ExtractedProduct[]) => new Set(xs.map((x) => x.category.toLowerCase())).size;
  try {
    // 1. Sitemaps.
    const want = Math.max(50, 20 * (opts.findMissing + opts.corpus));
    const fromSitemap = await discoverFromSitemaps(f, opts, want);
    stats.sitemapAndOther = f.requests;
    enqueueProducts('sitemap', shuffle(fromSitemap));
    console.log(`discovery: ${fromSitemap.length} product URLs from sitemaps`);

    // 2. Listing pages: explicit seeds always; defaults only when sitemaps gave nothing.
    const listingQ: Array<{ url: string; depth: number }> = [];
    const listingSeen = new Set<string>();
    const addListing = (raw: string, depth: number) => {
      let u: URL;
      try { u = new URL(raw, opts.base); } catch { return; }
      if (u.host !== host) { console.log(`  skipping seed on another host: ${raw}`); return; }
      u.hash = '';
      const key = u.toString();
      if (listingSeen.has(key)) return;
      listingSeen.add(key);
      listingQ.push({ url: key, depth });
    };
    for (const s of opts.seeds) addListing(s, 0);
    if (!fromSitemap.length) {
      for (const s of DEFAULT_SEEDS) addListing(s, 0);
      console.log(`discovery: crawling ${listingQ.length} seed pages instead`);
    }

    const fetchListing = async () => {
      const item = listingQ.shift()!;
      const pathname = new URL(item.url).pathname;
      if (!f.allowed(new URL(item.url).pathname + new URL(item.url).search)) { stats.skippedByRobots++; return; }
      const res = await f.get(item.url);
      stats.listingPages++;
      if (res.status !== 200) { stats.httpErrors++; console.log(`  [${f.requests}] listing ${pathname}: HTTP ${res.status}`); return; }
      const links = extractProductLinks(res.text, res.url);
      const more = extractListingLinks(res.text, res.url, { includeCategories: item.depth === 0 });
      enqueueProducts(pathname, links);
      for (const p of more.pagination) addListing(p, item.depth);
      for (const c of more.categories) addListing(c, item.depth + 1);
      console.log(`  [${f.requests}] listing ${pathname}: ${links.length} product links, ${more.pagination.length} pagination, ${more.categories.length} category`);
    };

    // Warm up: read a few listing pages first so products come from several
    // categories rather than whichever seed happened to be first.
    const warm = Math.min(listingQ.length, 6, Math.floor(opts.maxPages / 4));
    for (let i = 0; i < warm && !stopping && f.budgetLeft > 0; i++) await fetchListing();

    // 3. Product pages until both quotas are met or the budget runs out.
    const pnSeen = new Set<string>();
    const needMissing = () => candidates.length < opts.findMissing;
    const needCorpus = () =>
      opts.corpus > 0 && !(pool.length >= opts.corpus && (categoriesIn(pool) >= opts.corpus || pool.length >= 2 * opts.corpus));

    const fetchProduct = async (url: string) => {
      const pathname = new URL(url).pathname;
      if (!f.allowed(pathname)) { stats.skippedByRobots++; return; }
      const res = await f.get(url);
      stats.productPages++;
      if (res.status !== 200) { stats.httpErrors++; console.log(`  [${f.requests}] ${pathname}: HTTP ${res.status}`); return; }
      const p = extractProduct(res.text, res.url);
      const verdict = explainDescription(p.descriptionText, { name: p.name, partNumber: p.partNumber, title: p.title });
      stats.strategies[p.strategy]++;
      stats.status[verdict.status]++;
      console.log(`  [${f.requests}] ${pathname}: ${verdict.status} via ${p.strategy}${p.weak ? ' (weak)' : ''}, ${p.partNumber || 'no PN'}, "${p.name.slice(0, 50)}"`);
      const key = p.partNumber || p.url;
      if (pnSeen.has(key)) return;
      pnSeen.add(key);
      if (verdict.status === 'present') {
        if (!p.weak) pool.push(p);
      } else if (!p.partNumber) {
        stats.noPartNumber++;
      } else if (needMissing()) {
        candidates.push({ p, part: toCandidatePart(p, { id: 'tmp', harvestedAt, verdict }) });
      }
    };

    let turn = 0;
    while (!stopping && f.budgetLeft > 0 && (needMissing() || needCorpus())) {
      turn++;
      const preferParts = needMissing() && (!needCorpus() || turn % 2 === 1);
      const primary = preferParts ? partsQ : pQ;
      const secondary = preferParts ? pQ : partsQ;
      let next = primary.shift();
      if (!next && listingQ.length) { await fetchListing(); continue; }
      next ??= secondary.shift();
      if (!next) break;
      await fetchProduct(next);
    }
  } catch (err) {
    if (!(err instanceof FetchFailure) || stats.status.missing + stats.status.thin + stats.status.present === 0) throw err;
    aborted = err;
  }

  // 4. Write.
  await fs.mkdir(opts.outDir, { recursive: true });
  const written: string[] = [];
  const candidateParts = renumber(candidates.map((c) => c.part));
  const candPath = path.join(opts.outDir, 'products.candidates.json');
  await fs.writeFile(candPath, JSON.stringify(candidateParts, null, 2) + '\n');
  written.push(`${candPath} (${candidateParts.length} parts)`);

  const corpus = spreadByCategory(pool, opts.corpus).map(toCorpusSample);
  const corpusPath = path.join(opts.outDir, 'voice-corpus.json');
  let corpusNote = '';
  if (corpus.length) {
    await fs.writeFile(corpusPath, JSON.stringify(corpus, null, 2) + '\n');
    written.push(`${corpusPath} (${corpus.length} samples, ${categoriesIn(pool.filter((p) => corpus.some((c) => c.sourceUrl === p.url)))} categories)`);
    if (corpus.length < 6) corpusNote = `note: ${corpus.length} samples is below the 6 the UI needs to call the voice "fitted".`;
  } else {
    corpusNote = `voice-corpus.json NOT overwritten: no described listings were found.`;
  }

  if (opts.writeProducts) {
    const productsPath = path.join(opts.outDir, 'products.json');
    const merged = await mergeIntoProducts(productsPath, candidateParts);
    await fs.writeFile(productsPath, JSON.stringify(merged, null, 2) + '\n');
    written.push(`${productsPath} (${merged.length} parts, replaced)`);
  }

  // 5. Summary.
  const secs = ((Date.now() - started.getTime()) / 1000).toFixed(1);
  console.log('\n── Harvest summary ─────────────────────────────');
  console.log(`requests:     ${f.requests} of ${opts.maxPages} (sitemaps ${stats.sitemapAndOther}, listings ${stats.listingPages}, products ${stats.productPages}) in ${secs}s`);
  console.log(`strategies:   json-ld ${stats.strategies['json-ld']}, microdata ${stats.strategies.microdata}, container ${stats.strategies.container}, og:description ${stats.strategies['og-description']} (weak), none ${stats.strategies.none}`);
  console.log(`descriptions: missing ${stats.status.missing}, thin ${stats.status.thin}, present ${stats.status.present}`);
  if (stats.skippedByRobots || stats.httpErrors || stats.noPartNumber) {
    console.log(`skipped:      robots.txt ${stats.skippedByRobots}, HTTP errors ${stats.httpErrors}, no part number ${stats.noPartNumber}`);
  }
  console.log(`collected:    ${candidateParts.length}/${opts.findMissing} candidates, ${corpus.length}/${opts.corpus} corpus samples`);
  for (const w of written) console.log(`wrote:        ${w}`);
  if (corpusNote) console.log(corpusNote);
  if (!opts.writeProducts && candidateParts.length) console.log('data/products.json left unchanged (pass --write-products to replace it).');
  if (aborted) {
    console.error(`harvest: stopped early, ${aborted.host} ${aborted.detail} (on ${aborted.pathname}). Partial results above were written.`);
    return 1;
  }
  return 0;
}

/** Candidates become the new products.json. Where a harvested part number was
 *  already in the file, the human-written fields (summary, fitment, a better
 *  name or category) are carried over rather than thrown away. */
async function mergeIntoProducts(productsPath: string, candidates: CandidatePart[]): Promise<CandidatePart[]> {
  let existing: Array<Part & { statusNote?: string }> = [];
  try {
    existing = JSON.parse(await fs.readFile(productsPath, 'utf8'));
  } catch {
    existing = [];
  }
  const byPn = new Map(existing.map((p) => [p.partNumber.toUpperCase(), p]));
  const merged = candidates.map((c) => {
    const old = byPn.get(c.partNumber.toUpperCase());
    if (!old) return c;
    const generic = /^(genuine porsche part|part) /i.test(c.name);
    return {
      ...c,
      name: generic ? old.name : c.name,
      category: c.category === 'Uncategorised' ? old.category : c.category,
      summary: old.summary || c.summary,
      qualityTier: c.qualityTier === 'Unknown' ? old.qualityTier ?? c.qualityTier : c.qualityTier,
      ...(old.fitment ? { fitment: old.fitment } : {}),
    };
  });
  return renumber(merged);
}

async function main() {
  let opts: Options;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (err) {
    if (err instanceof UsageError) {
      console.error(`harvest: ${err.message}\n\n${USAGE}`);
      process.exit(2);
    }
    throw err;
  }
  try {
    process.exitCode = await run(opts);
  } catch (err) {
    if (err instanceof FetchFailure) {
      console.error(`harvest: cannot reach ${err.host}: ${err.detail} (on ${err.pathname}). Nothing was written.`);
      process.exit(1);
    }
    console.error(`harvest: ${(err as Error)?.message ?? err}`);
    if (process.env.HARVEST_DEBUG) console.error(err);
    process.exit(1);
  }
}

void main();
