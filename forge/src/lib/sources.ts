// Forge — who we trust, in what order.
//
// The policy lives in data/source-policy.json so it can be edited without
// touching code. Three tiers, plus a block list:
//   authorised — official Porsche dealership parts stores and Porsche itself.
//                Searched first, ranked first, and when they agree with each
//                other, their value wins a disagreement with any other source.
//   specialist — established Porsche parts retailers.
//   other      — anything else search turns up.
//   blocked    — never searched, read or counted (eBay).

import policy from '../../data/source-policy.json';
/** Second-level labels under which companies register (example.co.uk). */
const SECOND_LEVEL = new Set(['co', 'com', 'org', 'net', 'ac', 'gov', 'ltd', 'plc', 'me', 'edu']);

/** "shop.pelicanparts.com" and "forums.pelicanparts.com" are one company. */
export function registrableDomain(domain: string): string {
  const labels = domain.toLowerCase().replace(/^www\./, '').split('.').filter(Boolean);
  if (labels.length <= 2) return labels.join('.');
  const [sld, tld] = labels.slice(-2);
  const take = tld.length === 2 && SECOND_LEVEL.has(sld) ? 3 : 2;
  return labels.slice(-take).join('.');
}

export type SourceTier = 'authorised' | 'specialist' | 'other' | 'blocked';

interface Dealer {
  domain: string;
  name: string;
  /** Path template for the dealer's own site search, when known. */
  search?: string;
}

const DEALERS = new Map<string, Dealer>((policy.authorisedDealers as Dealer[]).map((d) => [d.domain, d]));
const SPECIALISTS = new Set<string>(policy.specialists);
const BLOCKED_BRANDS = new Set<string>(policy.blockedBrands);

export function sourceTier(domain: string): SourceTier {
  const company = registrableDomain(domain);
  if (BLOCKED_BRANDS.has(company.split('.')[0])) return 'blocked';
  if (DEALERS.has(company)) return 'authorised';
  if (SPECIALISTS.has(company)) return 'specialist';
  return 'other';
}

export const isBlocked = (domain: string) => sourceTier(domain) === 'blocked';
export const isAuthorised = (domain: string) => sourceTier(domain) === 'authorised';

export function dealerName(domain: string): string | undefined {
  return DEALERS.get(registrableDomain(domain))?.name;
}

export const TIER_RANK: Record<SourceTier, number> = { authorised: 0, specialist: 1, other: 2, blocked: 3 };

export function authorisedDealers(): Dealer[] {
  return [...DEALERS.values()];
}

export function blockedBrands(): string[] {
  return [...BLOCKED_BRANDS];
}
