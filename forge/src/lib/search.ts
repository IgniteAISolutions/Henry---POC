// Forge — finding a part somewhere other than Design 911.
//
// Providers are tried in order and the first configured one wins. Every
// provider returns the same shape, so the rest of the pipeline neither knows
// nor cares which one answered.

export interface SearchHit {
  url: string;
  title: string;
  snippet: string;
  domain: string;
}

import { authorisedDealers, blockedBrands, isBlocked, sourceTier, TIER_RANK } from './sources';

export type SearchProvider = 'google' | 'brave' | 'direct' | 'fixture';

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch (err) {
    // A malformed URL from a search provider is not worth a crash.
    if (!(err instanceof TypeError)) throw err;
    return '';
  }
}

/** Blocked sources removed; authorised dealers first, then specialists, then
 *  everything else, each group keeping the provider's own order. */
export function rank(hits: SearchHit[]): SearchHit[] {
  return hits
    .filter((h) => h.domain && !isBlocked(h.domain))
    .map((h, i) => ({ h, i }))
    .sort((a, b) => TIER_RANK[sourceTier(a.h.domain)] - TIER_RANK[sourceTier(b.h.domain)] || a.i - b.i)
    .map(({ h }) => h);
}

/** Query operators shared by Google and Brave. */
const EXCLUDE_BLOCKED = () =>
  blockedBrands().flatMap((b) => [`-site:${b}.com`, `-site:${b}.co.uk`, `-site:${b}.de`]).join(' ');
const DEALERS_ONLY = () => `(${authorisedDealers().map((d) => `site:${d.domain}`).join(' OR ')})`;

async function googleSearch(query: string, limit: number): Promise<SearchHit[]> {
  const key = process.env.GOOGLE_API_KEY;
  const cx = process.env.GOOGLE_CSE_ID;
  if (!key || !cx) return [];

  const url = new URL('https://www.googleapis.com/customsearch/v1');
  url.searchParams.set('key', key);
  url.searchParams.set('cx', cx);
  url.searchParams.set('q', query);
  url.searchParams.set('num', String(Math.min(limit, 10)));

  const res = await fetch(url, { signal: AbortSignal.timeout(6_000) });
  if (!res.ok) throw new Error(`Google CSE ${res.status}`);

  const data = (await res.json()) as { items?: Array<{ link: string; title: string; snippet: string }> };
  return (data.items ?? []).map((i) => ({
    url: i.link,
    title: i.title,
    snippet: i.snippet ?? '',
    domain: domainOf(i.link),
  }));
}

async function braveSearch(query: string, limit: number): Promise<SearchHit[]> {
  const key = process.env.BRAVE_API_KEY;
  if (!key) return [];

  const url = new URL('https://api.search.brave.com/res/v1/web/search');
  url.searchParams.set('q', query);
  url.searchParams.set('count', String(Math.min(limit, 20)));

  const res = await fetch(url, {
    headers: { Accept: 'application/json', 'X-Subscription-Token': key },
    signal: AbortSignal.timeout(6_000),
  });
  if (!res.ok) throw new Error(`Brave ${res.status}`);

  const data = (await res.json()) as {
    web?: { results?: Array<{ url: string; title: string; description: string }> };
  };
  return (data.web?.results ?? []).map((r) => ({
    url: r.url,
    title: r.title,
    snippet: r.description ?? '',
    domain: domainOf(r.url),
  }));
}

/** No search key configured. Build candidate URLs straight from each site's
 *  own search, authorised dealers first, and let the fetch stage follow them
 *  to product pages that carry the part number. Dealer search paths come from
 *  data/source-policy.json; a wrong path just 404s and is skipped. */
function directCandidates(partNumber: string): SearchHit[] {
  const pn = encodeURIComponent(partNumber);
  const dealers: SearchHit[] = authorisedDealers()
    .filter((d) => d.search)
    .map((d) => ({
      url: `https://www.${d.domain}${d.search!.replace('{pn}', pn)}`,
      domain: d.domain,
      title: `${d.name} search for ${partNumber}`,
      snippet: '',
    }));
  const specialists: Array<[string, string]> = [
    ['pelicanparts.com', `https://www.pelicanparts.com/cgi-bin/search/pelican_search.cgi?search_string=${pn}`],
    ['suncoastparts.com', `https://www.suncoastparts.com/search?q=${pn}`],
    ['fcpeuro.com', `https://www.fcpeuro.com/products?keywords=${pn}`],
    ['europaparts.com', `https://www.europaparts.com/catalogsearch/result/?q=${pn}`],
    ['autodoc.co.uk', `https://www.autodoc.co.uk/search?keyword=${pn}`],
    ['partsouq.com', `https://partsouq.com/en/search/all?q=${pn}`],
  ];
  return [
    ...dealers,
    ...specialists.map(([domain, url]) => ({ url, domain, title: `${domain} search for ${partNumber}`, snippet: '' })),
  ];
}

export interface SearchResult {
  hits: SearchHit[];
  provider: SearchProvider;
}

export async function searchByPartNumber(
  partNumber: string,
  context: { manufacturer?: string; name?: string } = {},
  limit = 10
): Promise<SearchResult> {
  // The part number is the anchor. Two queries run side by side: one limited
  // to authorised Porsche dealers, one open (minus blocked sources). Dealer
  // results go first.
  const base = [partNumber, context.manufacturer?.replace(/\(.*?\)/g, '').trim(), 'porsche'].filter(Boolean).join(' ');
  const dealerQuery = `${partNumber} ${DEALERS_ONLY()}`;
  const openQuery = `${base} ${EXCLUDE_BLOCKED()}`;

  const providers: Array<[SearchProvider, (q: string, n: number) => Promise<SearchHit[]>]> = [
    ['google', googleSearch],
    ['brave', braveSearch],
  ];

  for (const [provider, run] of providers) {
    try {
      const [dealer, open] = await Promise.all([run(dealerQuery, 5).catch(() => []), run(openQuery, limit)]);
      const seen = new Set<string>();
      const merged = [...dealer, ...open].filter((h) => (seen.has(h.url) ? false : (seen.add(h.url), true)));
      if (merged.length) return { hits: rank(merged).slice(0, limit), provider };
    } catch (err) {
      // A provider that errors or is unconfigured falls through to the next.
      console.warn(`[forge:search] ${provider} failed:`, (err as Error).message);
    }
  }

  return { hits: rank(directCandidates(partNumber)).slice(0, 14), provider: 'direct' };
}
