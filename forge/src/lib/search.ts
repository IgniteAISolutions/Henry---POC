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

export type SearchProvider = 'google' | 'brave' | 'direct' | 'fixture';

/** Sites that publish real Porsche part data and are worth reading.
 *  Ordered by how reliably they carry OE cross-references. */
const TRUSTED_DOMAINS = [
  'pelicanparts.com',
  'suncoastparts.com',
  'fcpeuro.com',
  'europaparts.com',
  'rennlist.com',
  'porscheapart.com',
  'autodoc.co.uk',
  'ecstuning.com',
  'partsouq.com',
  'sachs.com',
  'bosch-automotive.com',
];

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    // A malformed URL from a search provider is not worth a crash.
    return '';
  }
}

/** Trusted domains float to the top; everything else keeps its order. */
function rank(hits: SearchHit[]): SearchHit[] {
  const score = (h: SearchHit) => {
    const i = TRUSTED_DOMAINS.findIndex((d) => h.domain.endsWith(d));
    return i === -1 ? TRUSTED_DOMAINS.length : i;
  };
  return [...hits].sort((a, b) => score(a) - score(b));
}

async function googleSearch(query: string, limit: number): Promise<SearchHit[]> {
  const key = process.env.GOOGLE_API_KEY;
  const cx = process.env.GOOGLE_CSE_ID;
  if (!key || !cx) return [];

  const url = new URL('https://www.googleapis.com/customsearch/v1');
  url.searchParams.set('key', key);
  url.searchParams.set('cx', cx);
  url.searchParams.set('q', query);
  url.searchParams.set('num', String(Math.min(limit, 10)));

  const res = await fetch(url, { signal: AbortSignal.timeout(20_000) });
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
    signal: AbortSignal.timeout(20_000),
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

/** No search key configured. Build candidate URLs straight from each
 *  retailer's own search endpoint and let the fetch stage sort out which
 *  ones actually mention the part number. Slower and noisier than a real
 *  search API, but it needs no credentials at all. */
function directCandidates(partNumber: string): SearchHit[] {
  const pn = encodeURIComponent(partNumber);
  const endpoints: Array<[string, string]> = [
    ['pelicanparts.com', `https://www.pelicanparts.com/cgi-bin/search/pelican_search.cgi?search_string=${pn}`],
    ['suncoastparts.com', `https://www.suncoastparts.com/search?q=${pn}`],
    ['fcpeuro.com', `https://www.fcpeuro.com/products?keywords=${pn}`],
    ['europaparts.com', `https://www.europaparts.com/catalogsearch/result/?q=${pn}`],
    ['autodoc.co.uk', `https://www.autodoc.co.uk/search?keyword=${pn}`],
    ['partsouq.com', `https://partsouq.com/en/search/all?q=${pn}`],
  ];
  return endpoints.map(([domain, url]) => ({
    url,
    domain,
    title: `${domain} search for ${partNumber}`,
    snippet: '',
  }));
}

export interface SearchResult {
  hits: SearchHit[];
  provider: SearchProvider;
}

export async function searchByPartNumber(
  partNumber: string,
  context: { manufacturer?: string; name?: string } = {},
  limit = 8
): Promise<SearchResult> {
  // The part number is the anchor. Manufacturer and name only disambiguate
  // short or heavily reused numbers.
  const query = [partNumber, context.manufacturer, 'porsche'].filter(Boolean).join(' ');

  const providers: Array<[SearchProvider, () => Promise<SearchHit[]>]> = [
    ['google', () => googleSearch(query, limit)],
    ['brave', () => braveSearch(query, limit)],
  ];

  for (const [provider, run] of providers) {
    try {
      const hits = await run();
      if (hits.length) return { hits: rank(hits).slice(0, limit), provider };
    } catch (err) {
      // A provider that errors or is unconfigured falls through to the next.
      console.warn(`[forge:search] ${provider} failed:`, (err as Error).message);
    }
  }

  return { hits: directCandidates(partNumber).slice(0, limit), provider: 'direct' };
}
