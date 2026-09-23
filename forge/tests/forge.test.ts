// Forge regression suite. Each block pins a failure found in review, so the
// verification promises the demo makes cannot quietly regress.
//
//   npm test

import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import type { Evidence, Part } from '../src/lib/types';
import { verify, sameValue, registrableDomain, normYears } from '../src/lib/verify';
import { buildUserMessage } from '../src/lib/voice';
import { harvestEvidence, expandEndYear, extractEvidence } from '../src/lib/scrape';
import { sanitise, sanitiseText, findBanned } from '../src/lib/writer';
import { runPipeline } from '../src/lib/pipeline';
import { rank, searchByPartNumber } from '../src/lib/search';
import { sourceTier } from '../src/lib/sources';
import { loadParts } from '../src/lib/data';

const PN = '99610722553';
const part: Part = { id: 'x', partNumber: PN, manufacturer: 'Sachs', name: 'Clutch', category: 'c', summary: 's', descriptionStatus: 'missing' };
const ev = (domain: string, fields: Evidence['fields'], confirmed = true): Evidence => ({
  url: `https://${domain}/p`, domain, title: 't', snippet: '', partNumberConfirmed: confirmed, fields, fetchedAt: '', origin: 'live',
});
const payload = (evidence: Evidence[]) => buildUserMessage(part, verify(evidence, PN));

describe('verify: disputed facts never reach the writer', () => {
  test('conflicting spec-table rows are removed, not first-wins', () => {
    const msg = payload([
      ev('a.com', { material: 'Aluminium', specs: { Material: 'Aluminium', 'Outer diameter': '240 mm', Thread: 'M14x1.5' } }),
      ev('b.com', { material: 'Steel', specs: { Material: 'Steel', 'Outer diameter': '228 mm', Thread: 'M12x1.25' } }),
    ]);
    for (const leaked of ['Aluminium', 'Steel', '240 mm', '228 mm', 'M14', 'M12']) assert.ok(!msg.includes(leaked), `${leaked} leaked`);
  });

  test('a spec key named like a scalar cannot smuggle the scalar back in', () => {
    const msg = payload([ev('a.com', { weight: '1kg', specs: { weight: '1kg' } }), ev('b.com', { weight: '2kg', specs: { weight: '2kg' } })]);
    assert.ok(!msg.includes('1kg') && !msg.includes('2kg'));
  });

  test('each OE reference carries its own confidence', () => {
    const v = verify([ev('a.com', { oeReferences: ['99611608100', '95511111111'] }), ev('b.com', { oeReferences: ['99611608100'] })], PN);
    const byRef = Object.fromEntries(v.accepted.oeReferences.map((r) => [r.ref, r.confidence]));
    assert.equal(byRef['99611608100'], 'corroborated');
    assert.equal(byRef['95511111111'], 'single-source');
  });

  test('fitment years that disagree are dropped; the model still stands', () => {
    const v = verify([ev('a.com', { fitment: [{ model: '924S', engine: '2.5L', years: '1988' }] }), ev('b.com', { fitment: [{ model: '924S', years: '1985-89' }] })], PN);
    assert.deepEqual(v.accepted.fitment.map((f) => f.vehicle), ['924S']);
    assert.equal(v.accepted.fitment[0].confidence, 'corroborated');
    assert.equal(v.conflicts[0].kind, 'fitment-detail');
    assert.notEqual(v.verdict, 'conflicting');
  });

  test('a corroborated vehicle carries only corroborated detail', () => {
    const v = verify([ev('a.com', { fitment: [{ model: '997.2 Carrera', engine: '3.8L', years: '2009-12' }] }), ev('b.com', { fitment: [{ model: '997.2 Carrera' }] })], PN);
    assert.deepEqual(v.accepted.fitment.map((f) => f.vehicle), ['997.2 Carrera']);
  });

  test('fitment models match case-insensitively', () => {
    const v = verify([ev('a.com', { fitment: [{ model: 'Boxster' }] }), ev('b.com', { fitment: [{ model: 'BOXSTER' }] })], PN);
    assert.equal(v.accepted.fitment.length, 1);
    assert.equal(v.accepted.fitment[0].confidence, 'corroborated');
  });
});

describe('verify: what counts as independent agreement', () => {
  test('decimal commas compare as decimals', () => {
    assert.ok(sameValue('1.2 kg', '1,2 kg'));
    assert.ok(sameValue('1,200 g', '1200 g'));
    assert.ok(!sameValue('12 kg', '1,2 kg'));
  });

  test('subdomains of one company are one source', () => {
    assert.equal(registrableDomain('forums.pelicanparts.com'), 'pelicanparts.com');
    assert.equal(registrableDomain('shop.autodoc.co.uk'), 'autodoc.co.uk');
    const v = verify(['pelicanparts.com', 'forums.pelicanparts.com', 'shop.pelicanparts.com'].map((d) => ev(d, { material: 'Steel' })), PN);
    assert.equal(v.sourcesConfirming, 1);
    assert.notEqual(v.verdict, 'verified');
  });

  test('a company appearing twice keeps its confirming page', () => {
    const v = verify([ev('a.com', {}, false), ev('a.com', { material: 'Steel' }), ev('b.com', { material: 'Steel' })], PN);
    assert.equal(v.sourcesConfirming, 2);
    assert.deepEqual(v.accepted.attributes.map((a) => a.confidence), ['corroborated']);
  });

  test('three sources that agree on nothing are not "verified"', () => {
    const v = verify([ev('a.com', { material: 'Steel' }), ev('b.com', { weight: '1kg' }), ev('c.com', { position: 'Front' })], PN);
    assert.notEqual(v.verdict, 'verified');
  });

  test('year ranges normalise to house format', () => {
    assert.equal(normYears('1985-1989'), '1985-89');
    assert.equal(normYears('1997–2004'), '1997-04');
  });
});

describe('scrape: search pages and page noise are not evidence', () => {
  let base = '';
  let srv: http.Server;
  const pages: Record<string, string> = {
    '/search?q=99610722553': `<html><head><title>Search</title></head><body>
      <h1>Your search for "99610722553" returned 1 result</h1>
      <a href="/p/clutch-bearing-99610722553">Clutch bearing 996 107 225 53</a>
      <p>Call us free on 08001234567</p></body></html>`,
    '/search?q=00000000000': `<html><body><h1>Your search for "99610722553" returned 0 results</h1>
      <table><tr><td>Material</td><td>Cast iron</td></tr></table><p>Call 08001234567</p></body></html>`,
    '/p/clutch-bearing-99610722553': `<html><head><title>Clutch bearing 99610722553</title></head><body>
      <h1>Sachs clutch release bearing</h1>
      <table><tr><td>Material</td><td>Steel</td></tr></table>
      <p>Replaces OE 996 116 081 00. Fits 996 3.4L 1997-01. Sales line 08001234567.</p>
      <div class="related-products"><p>Also viewed: Cayenne 4.5L 2003-06 brake disc 95535140100</p></div></body></html>`,
    '/body-mention': `<html><head><title>Porsche parts</title></head><body><h1>Brake pads</h1><p>Unrelated item 99610722553 in a list.</p></body></html>`,
  };
  before(async () => {
    srv = http.createServer((q, r) => { r.setHeader('content-type', 'text/html'); r.end(pages[q.url!] ?? ''); });
    await new Promise<void>((ok) => srv.listen(0, '127.0.0.1', ok));
    base = `http://127.0.0.1:${(srv.address() as AddressInfo).port}`;
  });
  after(() => srv.close());

  test('a "0 results" page echoing the query produces no evidence', async () => {
    const out = await harvestEvidence({ url: `${base}/search?q=00000000000`, domain: 'shop.com', title: '', snippet: '' }, PN);
    assert.equal(out.length, 0);
  });

  test('a search page is followed one hop to the product page', async () => {
    const out = await harvestEvidence({ url: `${base}/search?q=99610722553`, domain: 'shop.com', title: '', snippet: '' }, PN);
    assert.equal(out.length, 1);
    assert.ok(out[0].partNumberConfirmed);
    assert.ok(out[0].url.includes('/p/clutch-bearing'));
    assert.equal(out[0].fields.specs?.Material, 'Steel');
  });

  test('phone numbers are not OE references; related products add no fitment', async () => {
    const [e] = await harvestEvidence({ url: `${base}/p/clutch-bearing-99610722553`, domain: 'shop.com', title: '', snippet: '' }, PN);
    assert.deepEqual(e.fields.oeReferences, ['99611608100']);
    assert.ok(!(e.fields.fitment ?? []).some((f) => /cayenne/i.test(f.model)));
    assert.deepEqual(e.fields.fitment, [{ model: '996', engine: '3.4L', years: '1997-01' }]);
  });

  test('a single passing mention in the body does not confirm the page', () => {
    const e = extractEvidence(pages['/body-mention'], `${base}/body-mention`, 'x.com', PN);
    assert.equal(e?.partNumberConfirmed, false);
  });

  test('two-digit end years keep the right century', () => {
    assert.equal(expandEndYear('1985', '89'), '1989');
    assert.equal(expandEndYear('1997', '04'), '2004');
  });
});

describe('writer: sanitiser keeps good copy and removes unsafe HTML', () => {
  test('en-dash year ranges survive as hyphenated ranges', () => {
    assert.equal(sanitise('<p>Fits 996 3.4L 1997–99, 2001–05.</p>'), '<p>Fits 996 3.4L 1997-99, 2001-05.</p>');
    assert.equal(sanitiseText('For the 996 — 1997–99!'), 'For the 996, 1997-99.');
  });

  test('attributes, scripts and unknown tags are stripped', () => {
    const out = sanitise('<p onmouseover="alert(1)">A</p><strong style="position:fixed">B</strong><script>alert(2)</script><img src=x onerror=alert(3)><!-- x! -->');
    assert.equal(out, '<p>A</p><strong>B</strong>');
  });

  test('only "Label: placeholder" lines are removed', () => {
    assert.equal(sanitise('<p>Replace both if the history is unknown.</p>'), '<p>Replace both if the history is unknown.</p>');
    assert.equal(sanitise('<p class="x">Material: N/A</p><p>Weight: Not specified<br>Qty: 1</p>'), '<p>Qty: 1</p>');
  });

  test('comparison signs in prose are not mistaken for tags', () => {
    assert.equal(sanitise('<p>Torque to < 25 Nm, then > 30 Nm.</p>'), '<p>Torque to < 25 Nm, then > 30 Nm.</p>');
  });

  test('banned phrases are detected, not deleted mid-sentence', () => {
    assert.deepEqual(findBanned('<p>A premium-grade seal, perfectly balanced. Rest assured.</p>'), ['premium', 'rest assured']);
    assert.equal(sanitise('<p>A premium-grade seal.</p>'), '<p>A premium-grade seal.</p>');
  });
});

describe('source policy: eBay never counts, authorised dealers win', () => {
  test('eBay is blocked on every country domain and never counted', () => {
    for (const d of ['ebay.com', 'www.ebay.co.uk', 'ebay.de']) assert.equal(sourceTier(d), 'blocked');
    const v = verify([ev('ebay.com', { material: 'Steel' }), ev('ebay.co.uk', { material: 'Steel' }), ev('a.com', { material: 'Steel' })], PN);
    assert.equal(v.sourcesChecked, 1);
    assert.equal(v.accepted.attributes[0].confidence, 'single-source');
  });

  test('search results drop eBay and put authorised dealers first', () => {
    const hit = (domain: string) => ({ url: `https://${domain}/x`, domain, title: '', snippet: '' });
    const ranked = rank([hit('random.com'), hit('ebay.com'), hit('pelicanparts.com'), hit('parts.byersporsche.com')]);
    assert.deepEqual(ranked.map((h) => h.domain), ['parts.byersporsche.com', 'pelicanparts.com', 'random.com']);
  });

  test('with no search key, dealer sites are queried first', async () => {
    const { hits, provider } = await searchByPartNumber(PN);
    assert.equal(provider, 'direct');
    assert.equal(sourceTier(hits[0].domain), 'authorised');
    assert.ok(!hits.some((h) => sourceTier(h.domain) === 'blocked'));
  });

  test('agreeing dealers overrule a retailer, and the overrule is recorded', () => {
    const v = verify([
      ev('porscheatlantaperimeterparts.com', { position: 'Front' }),
      ev('byersporsche.com', { position: 'Front' }),
      ev('rosepassion.com', { position: 'Rear left' }),
    ], PN);
    assert.equal(v.conflicts.length, 0);
    assert.equal(v.accepted.attributes[0].value, 'Front');
    assert.ok(v.accepted.attributes[0].authorised);
    assert.equal(v.overrides[0].overruled[0].value, 'Rear left');
    assert.ok(!buildUserMessage(part, v).includes('Rear left'));
  });

  test('dealers that disagree with each other settle nothing', () => {
    const v = verify([ev('sunsetporscheparts.com', { material: 'Steel' }), ev('byersporsche.com', { material: 'Aluminium' })], PN);
    assert.equal(v.conflicts.length, 1);
    assert.equal(v.accepted.attributes.length, 0);
  });

  test('a dealer-backed year range wins a fitment-detail disagreement', () => {
    const v = verify([
      ev('sunsetporscheparts.com', { fitment: [{ model: '996', years: '1997-01' }] }),
      ev('rosepassion.com', { fitment: [{ model: '996', years: '1998' }] }),
    ], PN);
    assert.deepEqual(v.accepted.fitment.map((f) => f.vehicle), ['996 1997-01']);
    assert.equal(v.overrides[0].kind, 'fitment-detail');
  });
});

describe('recorded demo run', () => {
  test('the 10 parts land where the demo script says they do', async () => {
    const parts = await loadParts();
    const got: Record<string, string> = {};
    for (const p of parts) got[p.partNumber] = (await runPipeline(p, { mode: 'recorded' })).verification.verdict;
    assert.equal(got['94411021401'], 'verified');
    assert.equal(got['92863210100'], 'verified');
    assert.equal(got['99750396302GRV'], 'verified');
    assert.equal(got['V04015005BT'], 'unconfirmed');
    assert.equal(got['9P1601147K8Z8'], 'unconfirmed');
    assert.equal(Object.values(got).filter((v) => v !== 'unconfirmed').length, 8);
  });

  test('no eBay evidence remains in the recorded fixtures', async () => {
    const { loadFixtures } = await import('../src/lib/data');
    const all = Object.values(await loadFixtures()).flat();
    assert.ok(!all.some((e) => sourceTier(e.domain) === 'blocked'));
  });

  test('door sill: the dealers\' Front wins, Rear left never reaches the writer', async () => {
    const p = (await loadParts()).find((x) => x.partNumber === '99750396302GRV')!;
    const r = await runPipeline(p, { mode: 'recorded' });
    const msg = buildUserMessage(p, r.verification);
    assert.ok(msg.includes('"Front"'));
    assert.ok(!msg.includes('Rear left'));
    assert.equal(r.verification.overrides[0].field, 'Position');
  });
});
