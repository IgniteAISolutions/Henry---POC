// Tests for the harvester. Run: npx tsx --test scripts/harvest-lib.test.ts
//
// Every fixture below is SYNTHETIC. They mimic what search-index results show
// of design911.co.uk (bare /parts/<PN>/ pages, rich /p/<slug>/ pages, category
// listings) because the machine that wrote them could not reach the live site.
// When a real page breaks a heuristic, paste its markup in as a new fixture.

import { test, describe, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { promises as fs } from 'node:fs';
import { execFile } from 'node:child_process';
import type { AddressInfo } from 'node:net';
import {
  classifyDescription,
  cleanName,
  decodeEntities,
  explainDescription,
  extractListingLinks,
  extractProduct,
  extractProductLinks,
  htmlToText,
  isAllowed,
  looksLikePartNumber,
  manufacturerFor,
  parseRobots,
  parseSitemap,
  partNumberFromTitle,
  partNumberFromUrl,
  renumber,
  sanitiseDescriptionHtml,
  spreadByCategory,
  stripBoilerplate,
  THIN_THRESHOLD_CHARS,
  toCandidatePart,
  toCorpusSample,
} from './harvest-lib';

// ── Fixtures ─────────────────────────────────────────────────────────

const BASE = 'https://www.design911.co.uk';

const CHROME_HEAD = `
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width">
  <link rel="stylesheet" href="/css/site.css">`;
const CHROME_NAV = `
  <header><nav class="main-nav">
    <a href="/">Home</a> <a href="/b/original/">Original Porsche</a>
    <div class="description">Dedicated to your Porsche needs</div>
  </nav></header>`;
const CHROME_FOOTER = `
  <footer><p>Dedicated to your Porsche needs. Free UK delivery on orders over £50.</p>
  <a href="/parts/99761209005/">Recently viewed</a></footer>`;

/** A bare /parts/ page: title is just the part number, description tab empty. */
const BARE_PARTS_PAGE = `<!doctype html><html><head>${CHROME_HEAD}
  <title>Original Porsche Part - 99761209005 | Design911</title>
  <meta property="og:description" content="Dedicated to your Porsche needs">
</head><body>${CHROME_NAV}
  <div class="breadcrumb"><ul><li>Home</li><li>Original Porsche</li><li>99761209005</li></ul></div>
  <h1>Original Porsche Part - 99761209005</h1>
  <div class="price-box"><span class="price">£48.30</span></div>
  <ul class="nav-tabs"><li><a href="#tab-description">Description</a></li></ul>
  <div class="tab-content"><div id="tab-description" class="tab-pane"> 99761209005 </div></div>
  <div class="related"><a href="/parts/92863210100/">Glove box light</a></div>
${CHROME_FOOTER}</body></html>`;

/** A /parts/ page whose title carries a name: "Glove box light Genuine Porsche part <PN>". */
const GLOVE_BOX_PAGE = `<!doctype html><html><head>
  <title>Glove box light Genuine Porsche part 92863210100 | Design911</title>
</head><body>${CHROME_NAV}
  <h1>Glove box light Genuine Porsche part 92863210100</h1>
  <div id="tab-description"><p>Glove box light 92863210100. Genuine Porsche part.</p></div>
${CHROME_FOOTER}</body></html>`;

/** Site-wide boilerplate only: the title and the description say nothing. */
const BOILERPLATE_PAGE = `<!doctype html><html><head>
  <title>Dedicated to your Porsche needs</title>
  <meta property="og:description" content="Dedicated to your Porsche needs">
</head><body>${CHROME_NAV}
  <div class="product-description"><p>Dedicated to your Porsche needs.</p><p>Free UK delivery on orders over £50. Call us on 01234 567890.</p></div>
${CHROME_FOOTER}</body></html>`;

const RICH_DESCRIPTION_HTML = `
  <h3 class="tab-title" style="color:red">Water thermostat gasket</h3>
  <p class="intro" data-x="1">Porsche 996 Turbo Water thermostat gasket <span>99610632671</span>, which fits
     Porsche 996 Turbo 3.6L 2001-05, Porsche 997 Turbo 3.6L 2007-09 and Porsche 997 GT2 3.6L 2008-09.</p>
  <script>trackView('99610632671')</script>
  <img src="/img/gasket.jpg" alt="gasket">
  <div>Supplied by <a href="/b/elring/">ELRING</a>, the original equipment supplier to Porsche.</div>
  <ol><li><b>Material:</b> <em>metal-elastomer</em></li><li>Quantity: 1 per thermostat housing</li></ol>
  <p>Bolts are part number 90038502501 (you will need x2).</p>
  <iframe src="https://www.youtube.com/embed/x"></iframe>`;

/** JSON as a CMS would embed it in a <script>: "</" escaped so an HTML
 *  fragment inside a string cannot close the script element early. */
const jsonForScript = (v: unknown) => JSON.stringify(v).replace(/<\//g, '<\\/');

/** A rich /p/ page with JSON-LD Product, a breadcrumb list and a description tab. */
const RICH_P_PAGE = `<!doctype html><html><head>${CHROME_HEAD}
  <title>ELRING 237.871 or 237.870 Porsche 99610632671 99610632670 Water thermostat gasket for Porsche 996 Turbo and 997 Turbo - 99610632671/1 | Design 911</title>
  <meta property="og:description" content="Water thermostat gasket for Porsche 996 Turbo and 997 Turbo">
  <script type="application/ld+json">
  {"@context":"https://schema.org","@graph":[
    {"@type":"BreadcrumbList","itemListElement":[
      {"@type":"ListItem","position":1,"name":"Home","item":"${BASE}/"},
      {"@type":"ListItem","position":2,"name":"Water & Coolant","item":"${BASE}/porsche/996--911--1997-05/water---coolant-pumps/"},
      {"@type":"ListItem","position":3,"name":"Water thermostat gasket"}]},
    {"@type":"Product",
     "name":"ELRING Water thermostat gasket for Porsche 996 Turbo and 997 Turbo",
     "sku":"99610632671/1","mpn":"99610632671",
     "brand":{"@type":"Brand","name":"ELRING"},
     "category":"Porsche > 996 > Water &amp; Coolant Pumps",
     "description":${jsonForScript(RICH_DESCRIPTION_HTML)},
     "offers":{"@type":"Offer","price":"12.50","priceCurrency":"GBP","availability":"https://schema.org/InStock"}}
  ]}
  </script>
</head><body>${CHROME_NAV}
  <h1>ELRING Water thermostat gasket for Porsche 996 Turbo and 997 Turbo</h1>
  <div class="tab-content">
    <div class="tab-pane" id="tab-reviews">No reviews yet.</div>
    <div class="tab-pane" id="tab-description">${RICH_DESCRIPTION_HTML}</div>
  </div>
  <a href="/p/ignition-coil-pack-boxster-986/">Related</a>
${CHROME_FOOTER}</body></html>`;

/** Rich page with no JSON-LD: microdata only. */
const MICRODATA_PAGE = `<!doctype html><html><head><title>Ignition coil pack for Porsche Boxster 986 | Design 911</title></head><body>
  <div itemscope itemtype="https://schema.org/Product">
    <h1 itemprop="name">Bosch Ignition Coil Pack</h1>
    <span itemprop="sku">99760210500</span>
    <span itemprop="brand">Bosch</span>
    <meta itemprop="category" content="Ignition Coils">
    <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
      <meta itemprop="price" content="89.95"><meta itemprop="priceCurrency" content="GBP">
    </div>
    <div itemprop="description"><p>These ignition coil packs fit Porsche Boxster 986 2.5L 1997-99, Boxster 986 2.7L 2000-04 and Boxster S 986 3.2L 2000-04.</p><p>One coil per cylinder, six required per engine.</p></div>
  </div></body></html>`;

/** Only an og:description has content. Should be used, flagged weak. */
const OG_ONLY_PAGE = `<!doctype html><html><head>
  <title>Genuine Porsche part 99610612300 | Design911</title>
  <meta property="og:description" content="Coolant expansion tank cap for Porsche 996 and Boxster 986, opens at 1.4 bar.">
</head><body><h1>99610612300</h1></body></html>`;

/** A short description: something real, but not much. */
const THIN_PAGE = `<!doctype html><html><head><title>Water pump - 99610601176 | Design911</title></head><body>
  <h1>Water pump</h1>
  <div id="tab-description"><p>Water pump for Porsche 996 3.4L, supplied with gasket.</p></div></body></html>`;

/** A category listing with pagination and noisy links. */
const LISTING_PAGE = `<!doctype html><html><head>
  <title>Water & Coolant Pumps | Porsche 996 | Design911</title>
  <link rel="next" href="/porsche/996--911--1997-05/water---coolant-pumps/2/">
</head><body>${CHROME_NAV}
  <div class="products">
    <a href="/p/elring-thermostat-gasket-996-turbo/">Gasket</a>
    <a href="https://www.design911.co.uk/p/elring-thermostat-gasket-996-turbo/?ref=list#top">Gasket again</a>
    <a href="/p/water-pump-996/">Water pump</a>
    <a href="/parts/99610601176">Water pump bare</a>
    <a href="/parts/99610601176/?utm=x">Water pump bare dup</a>
    <a href="https://www.design911.com/p/mirror-item/">Mirror (other host)</a>
    <a href="https://www.example.com/p/foreign/">Foreign</a>
    <a href="/basket/">Basket</a>
    <a href="javascript:void(0)">JS</a>
    <a href="mailto:sales@design911.co.uk">Mail</a>
  </div>
  <div class="pagination">
    <a href="/porsche/996--911--1997-05/water---coolant-pumps/">1</a>
    <a href="/porsche/996--911--1997-05/water---coolant-pumps/2/">2</a>
    <a href="/porsche/996--911--1997-05/water---coolant-pumps/3/">3</a>
  </div>
  <div class="side-cats"><a href="/porsche/boxster-986-987-981/ignition-coils/">Ignition coils</a></div>
${CHROME_FOOTER}</body></html>`;

const ROBOTS_TXT = `# Design 911 robots (synthetic)
User-agent: *
Disallow: /checkout/
Disallow: /basket
Disallow: /search
Allow: /search/help
Disallow: /*?sort=
Disallow: /*.pdf$
Crawl-delay: 2

User-agent: BadBot
User-agent: EvilScraper
Disallow: /

Sitemap: https://www.design911.co.uk/sitemap.xml
Sitemap: https://www.design911.co.uk/sitemap-products.xml
`;

const SITEMAP_INDEX = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.design911.co.uk/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://www.design911.co.uk/sitemap-products.xml</loc><lastmod>2026-09-01</lastmod></sitemap>
</sitemapindex>`;

const SITEMAP_URLSET = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.design911.co.uk/parts/99761209005/</loc></url>
  <url><loc> https://www.design911.co.uk/p/elring-thermostat-gasket-996-turbo/ </loc><changefreq>weekly</changefreq></url>
  <url><loc>https://www.design911.co.uk/parts/99761209005/</loc></url>
</urlset>`;

// ── Part numbers and names ───────────────────────────────────────────

describe('part numbers', () => {
  test('looksLikePartNumber accepts Porsche formats, rejects noise', () => {
    for (const pn of ['99761209005', '9A110622502', 'V04015005BT', '99610632671']) assert.ok(looksLikePartNumber(pn), pn);
    for (const no of ['237.871', '1997-05', 'Porsche', '996', 'ABCDEFGHIJK', '']) assert.ok(!looksLikePartNumber(no), no);
  });

  test('partNumberFromUrl reads /parts/<PN>/', () => {
    assert.equal(partNumberFromUrl(`${BASE}/parts/99761209005/`), '99761209005');
    assert.equal(partNumberFromUrl(`${BASE}/parts/v04015005bt`), 'V04015005BT');
    assert.equal(partNumberFromUrl(`${BASE}/p/some-slug/`), '');
    assert.equal(partNumberFromUrl('not a url'), '');
  });

  test('partNumberFromTitle prefers the trailing "- PN/1" suffix', () => {
    assert.equal(partNumberFromTitle('Original Porsche Part - 99761209005 | Design911'), '99761209005');
    assert.equal(partNumberFromTitle('Glove box light Genuine Porsche part 92863210100'), '92863210100');
    assert.equal(
      partNumberFromTitle('ELRING 237.871 or 237.870 Porsche 99610632670 99610632671 Water thermostat gasket - 99610632671/1 | Design 911'),
      '99610632671'
    );
    assert.equal(partNumberFromTitle('Dedicated to your Porsche needs'), '');
  });

  test('cleanName strips site suffix, PN and "Genuine Porsche part"', () => {
    assert.equal(cleanName('Glove box light Genuine Porsche part 92863210100 | Design911', '92863210100'), 'Glove box light');
    assert.equal(cleanName('Original Porsche Part - 99761209005 | Design911', '99761209005'), '');
    assert.equal(cleanName('Dedicated to your Porsche needs', ''), '');
  });
});

// ── Sanitiser ────────────────────────────────────────────────────────

describe('sanitiseDescriptionHtml', () => {
  const out = sanitiseDescriptionHtml(RICH_DESCRIPTION_HTML);

  test('keeps only p, br, ul, li, strong', () => {
    const tags = [...out.matchAll(/<\/?([a-z0-9]+)/gi)].map((m) => m[1].toLowerCase());
    assert.ok(tags.length > 0);
    for (const t of tags) assert.ok(['p', 'br', 'ul', 'li', 'strong'].includes(t), `unexpected <${t}> in ${out}`);
  });

  test('strips every attribute', () => {
    assert.doesNotMatch(out, /<[a-z]+\s+[^>]*=/i);
  });

  test('drops script, iframe and img content entirely', () => {
    assert.doesNotMatch(out, /trackView|youtube|gasket\.jpg/);
  });

  test('keeps text from unwrapped inline tags and maps b→strong, ol→ul, heading→p>strong, div→p', () => {
    assert.match(out, /99610632671/);
    assert.match(out, /<p><strong>Water thermostat gasket<\/strong><\/p>/);
    assert.match(out, /<ul><li><strong>Material:<\/strong> metal-elastomer<\/li><li>Quantity: 1 per thermostat housing<\/li><\/ul>/);
    assert.match(out, /<p>Supplied by ELRING, the original equipment supplier to Porsche\.<\/p>/);
    assert.match(out, /<p>Bolts are part number 90038502501 \(you will need x2\)\.<\/p>/);
  });

  test('wraps loose text, removes empties, keeps br, escapes text', () => {
    assert.equal(sanitiseDescriptionHtml('Loose text <span>here</span>'), '<p>Loose text here</p>');
    assert.equal(sanitiseDescriptionHtml('<p></p><p> <br> </p><strong></strong><p>Real</p>'), '<p>Real</p>');
    assert.equal(sanitiseDescriptionHtml('<p>One<br/>Two</p>'), '<p>One<br>Two</p>');
    assert.equal(sanitiseDescriptionHtml('<p>5 &lt; 6 &amp; true</p>'), '<p>5 &lt; 6 &amp; true</p>');
    assert.equal(sanitiseDescriptionHtml('<p onclick="x()"><a href="javascript:alert(1)">Click</a></p>'), '<p>Click</p>');
    assert.equal(sanitiseDescriptionHtml(''), '');
  });
});

// ── Classifier ───────────────────────────────────────────────────────

describe('classifyDescription', () => {
  test('empty is missing', () => {
    assert.equal(classifyDescription(''), 'missing');
    assert.equal(classifyDescription('   \n '), 'missing');
  });

  test('boilerplate only is missing', () => {
    assert.equal(classifyDescription('Dedicated to your Porsche needs'), 'missing');
    assert.equal(explainDescription('Dedicated to your Porsche needs. Free UK delivery on orders over £50.').reason, 'boilerplate only');
  });

  test('restating the name / part number is missing', () => {
    const ctx = { name: 'Battery Cable', partNumber: '99761209005' };
    assert.equal(classifyDescription('Battery Cable 99761209005. Genuine Porsche part.', ctx), 'missing');
    assert.equal(classifyDescription('99761209005', ctx), 'missing');
    assert.equal(explainDescription('Battery cable for the Porsche 997', ctx).reason, 'only restates the name / part number');
  });

  test(`under ${THIN_THRESHOLD_CHARS} chars of real content is thin`, () => {
    const v = explainDescription('Water pump for Porsche 996 3.4L, supplied with gasket.', { name: 'Water pump', partNumber: '99610601176' });
    assert.equal(v.status, 'thin');
    assert.ok(v.realContentLength < THIN_THRESHOLD_CHARS);
  });

  test('boilerplate does not count toward length', () => {
    const text = 'Water pump for Porsche 996 3.4L, supplied with gasket. Dedicated to your Porsche needs. Free UK delivery on all orders over fifty pounds, we ship worldwide.';
    assert.ok(text.length > THIN_THRESHOLD_CHARS);
    assert.equal(classifyDescription(text), 'thin');
    assert.equal(stripBoilerplate(text), 'Water pump for Porsche 996 3.4L, supplied with gasket.');
  });

  test('real fitment copy is present', () => {
    const text =
      'Porsche 997 Water pump Thermostat 9A110622502, which fits Porsche 987.2 Boxster 2009-12, Porsche 987C.2 Cayman 2009-12 and Porsche 997.2 Carrera 2009-12. Bolts are part number 90038502501 (you will need x12).';
    assert.equal(classifyDescription(text, { name: 'Water pump Thermostat', partNumber: '9A110622502' }), 'present');
  });

  test('accepts HTML input', () => {
    assert.equal(classifyDescription('<p>Dedicated to your Porsche needs</p>'), 'missing');
  });
});

// ── extractProduct ───────────────────────────────────────────────────

describe('extractProduct', () => {
  test('bare /parts/ page: PN from URL/title, description missing, nav/footer boilerplate ignored', () => {
    const p = extractProduct(BARE_PARTS_PAGE, `${BASE}/parts/99761209005/`);
    assert.equal(p.pageType, 'parts');
    assert.equal(p.partNumber, '99761209005');
    assert.equal(p.genuine, true);
    assert.equal(p.name, 'Genuine Porsche part 99761209005');
    assert.equal(p.category, 'Original Porsche');
    assert.equal(classifyDescription(p.descriptionText, p), 'missing');
    assert.doesNotMatch(p.descriptionText, /Dedicated/);
  });

  test('named /parts/ page: name from title, restated description is missing', () => {
    const p = extractProduct(GLOVE_BOX_PAGE, `${BASE}/parts/92863210100/`);
    assert.equal(p.partNumber, '92863210100');
    assert.equal(p.name, 'Glove box light');
    assert.equal(p.strategy, 'container');
    assert.equal(classifyDescription(p.descriptionText, p), 'missing');
  });

  test('boilerplate-only page is missing and gets a fallback name', () => {
    const p = extractProduct(BOILERPLATE_PAGE, `${BASE}/parts/96410601401/`);
    assert.equal(p.partNumber, '96410601401');
    assert.equal(p.name, 'Part 96410601401');
    assert.equal(p.genuine, false);
    assert.equal(p.weak, false, 'og:description boilerplate must not be promoted');
    assert.equal(classifyDescription(p.descriptionText, p), 'missing');
  });

  test('rich /p/ page: JSON-LD wins, fields merged and sanitised', () => {
    const p = extractProduct(RICH_P_PAGE, `${BASE}/p/elring-thermostat-gasket-996-turbo/`);
    assert.equal(p.pageType, 'p');
    assert.equal(p.strategy, 'json-ld');
    assert.equal(p.weak, false);
    assert.equal(p.partNumber, '99610632671');
    assert.equal(p.name, 'ELRING Water thermostat gasket for Porsche 996 Turbo and 997 Turbo');
    assert.equal(p.brand, 'ELRING');
    assert.equal(p.category, 'Water & Coolant Pumps');
    assert.equal(p.price, '£12.50');
    assert.match(p.descriptionHtml, /^<p>/);
    assert.doesNotMatch(p.descriptionHtml, /<(script|img|iframe|span|a|div|h3|ol|em|b)\b/);
    assert.match(p.descriptionText, /fits Porsche 996 Turbo 3\.6L 2001-05/);
    assert.equal(classifyDescription(p.descriptionText, p), 'present');
  });

  test('rich page without JSON-LD falls to the description tab (container)', () => {
    const noLd = RICH_P_PAGE.replace(/<script type="application\/ld\+json">[\s\S]*?<\/script>/, '');
    const p = extractProduct(noLd, `${BASE}/p/elring-thermostat-gasket-996-turbo/`);
    assert.equal(p.strategy, 'container');
    assert.match(p.descriptionText, /Bolts are part number 90038502501/);
    assert.doesNotMatch(p.descriptionText, /No reviews yet/, 'picks the description pane, not the first pane');
    assert.equal(p.partNumber, '99610632671', 'PN from the title suffix');
    assert.equal(p.category, '', 'no JSON-LD and no visible breadcrumb: category left blank, never guessed');
  });

  test('flat JSON-LD text gives way to the same copy with paragraph structure', () => {
    const flat = htmlToText(RICH_DESCRIPTION_HTML);
    const html = RICH_P_PAGE.replace(jsonForScript(RICH_DESCRIPTION_HTML), jsonForScript(flat));
    assert.notEqual(html, RICH_P_PAGE);
    const p = extractProduct(html, `${BASE}/p/elring-thermostat-gasket-996-turbo/`);
    assert.equal(p.strategy, 'container');
    assert.ok((p.descriptionHtml.match(/<p>/g) ?? []).length >= 3);
  });

  test('microdata page', () => {
    const p = extractProduct(MICRODATA_PAGE, `${BASE}/p/ignition-coil-pack-boxster-986/`);
    assert.equal(p.strategy, 'microdata');
    assert.equal(p.name, 'Bosch Ignition Coil Pack');
    assert.equal(p.partNumber, '99760210500');
    assert.equal(p.category, 'Ignition Coils');
    assert.equal(p.price, '£89.95');
    assert.equal(p.brand, 'Bosch');
    assert.equal(p.descriptionHtml.startsWith('<p>These ignition coil packs fit Porsche Boxster 986 2.5L 1997-99'), true);
    assert.equal(classifyDescription(p.descriptionText, p), 'present');
  });

  test('og:description is a last resort and flagged weak', () => {
    const p = extractProduct(OG_ONLY_PAGE, `${BASE}/parts/99610612300/`);
    assert.equal(p.strategy, 'og-description');
    assert.equal(p.weak, true);
    assert.match(p.descriptionText, /expansion tank cap/);
  });

  test('thin description', () => {
    const p = extractProduct(THIN_PAGE, `${BASE}/parts/99610601176/`);
    assert.equal(p.name, 'Water pump');
    assert.equal(classifyDescription(p.descriptionText, p), 'thin');
  });

  test('broken JSON-LD (trailing comma) is tolerated; nonsense is skipped', () => {
    const html = `<html><head><title>x</title>
      <script type="application/ld+json">{"@type":"Product","name":"Oil filter","sku":"99610722553","description":"Oil filter for Porsche 996 and 997 Carrera, fits 3.4L and 3.6L engines 1997-08. Replace at every oil service, one per engine, supplied with sealing ring.",}</script>
      <script type="application/ld+json">{not json</script></head><body></body></html>`;
    const p = extractProduct(html, `${BASE}/p/oil-filter/`);
    assert.equal(p.strategy, 'json-ld');
    assert.equal(p.name, 'Oil filter');
    assert.equal(p.partNumber, '99610722553');
  });

  test('no description anywhere reports strategy none', () => {
    const p = extractProduct('<html><head><title>Original Porsche Part - 99761209005 | Design911</title></head><body></body></html>', `${BASE}/parts/99761209005/`);
    assert.equal(p.strategy, 'none');
    assert.equal(p.descriptionHtml, '');
  });
});

// ── Mapping to Forge shapes ──────────────────────────────────────────

describe('toCorpusSample / toCandidatePart', () => {
  test('corpus sample carries sanitised HTML and source', () => {
    const p = extractProduct(RICH_P_PAGE, `${BASE}/p/elring-thermostat-gasket-996-turbo/`);
    const s = toCorpusSample(p);
    assert.deepEqual(Object.keys(s).sort(), ['category', 'longHtml', 'name', 'partNumber', 'sourceUrl']);
    assert.equal(s.partNumber, '99610632671');
    assert.equal(s.longHtml, p.descriptionHtml);
    assert.equal(s.sourceUrl, `${BASE}/p/elring-thermostat-gasket-996-turbo/`);
  });

  test('candidate from a genuine bare page', () => {
    const p = extractProduct(BARE_PARTS_PAGE, `${BASE}/parts/99761209005/`);
    const c = toCandidatePart(p, { id: 'p07', harvestedAt: '2026-09-23T10:00:00Z' });
    assert.equal(c.id, 'p07');
    assert.equal(c.manufacturer, 'Porsche (Genuine)');
    assert.equal(c.qualityTier, 'Genuine');
    assert.equal(c.summary, '');
    assert.equal(c.descriptionStatus, 'missing');
    assert.equal(c.sourceUrl, `${BASE}/parts/99761209005/`);
    assert.equal(c.existingDescription, undefined);
    assert.match(c.statusNote, /^Harvested from design911\.co\.uk on 2026-09-23T10:00:00Z: description missing/);
  });

  test('thin candidate keeps the existing text; non-genuine brand is kept', () => {
    const p = extractProduct(THIN_PAGE, `${BASE}/parts/99610601176/`);
    const c = toCandidatePart(p, { id: 'p01', harvestedAt: 'now' });
    assert.equal(c.descriptionStatus, 'thin');
    assert.equal(c.existingDescription, 'Water pump for Porsche 996 3.4L, supplied with gasket.');
    assert.equal(c.manufacturer, 'Unknown');
    assert.equal(c.qualityTier, 'Unknown');
    assert.equal(manufacturerFor({ brand: 'Bosch', genuine: false }), 'Bosch');
    assert.equal(manufacturerFor({ brand: 'Porsche', genuine: false }), 'Porsche (Genuine)');
  });

  test('renumber and spreadByCategory', () => {
    assert.deepEqual(renumber([{ id: 'x' }, { id: 'y' }]).map((r) => r.id), ['p01', 'p02']);
    assert.equal(renumber(Array.from({ length: 120 }, () => ({ id: '' })))[119].id, 'p120');
    const items = [
      { category: 'Water', pageType: 'p', n: 1 },
      { category: 'Water', pageType: 'p', n: 2 },
      { category: 'Water', pageType: 'p', n: 3 },
      { category: 'Brakes', pageType: 'parts', n: 4 },
      { category: 'Ignition', pageType: 'p', n: 5 },
    ];
    const picked = spreadByCategory(items, 3).map((i) => i.n);
    assert.deepEqual(picked, [1, 5, 4], 'one per category, /p/ categories first');
    assert.equal(spreadByCategory(items, 10).length, 5);
  });
});

// ── robots.txt ───────────────────────────────────────────────────────

describe('parseRobots / isAllowed', () => {
  const star = parseRobots(ROBOTS_TXT, 'ForgeHarvester');

  test('parses the * group, crawl-delay and sitemaps', () => {
    assert.equal(star.agent, '*');
    assert.equal(star.crawlDelaySeconds, 2);
    assert.deepEqual(star.sitemaps, [`${BASE}/sitemap.xml`, `${BASE}/sitemap-products.xml`]);
    assert.ok(star.disallow.includes('/checkout/'));
  });

  test('product and listing pages are allowed; disallowed paths are not', () => {
    assert.ok(isAllowed(star, '/parts/99761209005/'));
    assert.ok(isAllowed(star, '/p/some-slug/'));
    assert.ok(isAllowed(star, `${BASE}/porsche/996--911--1997-05/water---coolant-pumps/2/`));
    assert.ok(!isAllowed(star, '/checkout/step1'));
    assert.ok(!isAllowed(star, '/basket'));
    assert.ok(!isAllowed(star, '/search?q=pump'));
  });

  test('longest match wins, Allow wins ties, wildcards and $ anchors work', () => {
    assert.ok(isAllowed(star, '/search/help'));
    assert.ok(!isAllowed(star, '/porsche/996/?sort=price'));
    assert.ok(!isAllowed(star, '/files/catalogue.pdf'));
    assert.ok(isAllowed(star, '/files/catalogue.pdf?download=1'));
    assert.ok(isAllowed(parseRobots('User-agent: *\nDisallow: /p/\nAllow: /p/'), '/p/x/'));
  });

  test('a group naming our agent (multi-line User-agent) wins over *', () => {
    const bad = parseRobots(ROBOTS_TXT, 'Mozilla/5.0 (compatible; EvilScraper/1.0)');
    assert.equal(bad.agent, 'Mozilla/5.0 (compatible; EvilScraper/1.0)');
    assert.ok(!isAllowed(bad, '/parts/99761209005/'));
  });

  test('empty Disallow and missing file allow everything', () => {
    assert.ok(isAllowed(parseRobots('User-agent: *\nDisallow:'), '/anything'));
    assert.ok(isAllowed(parseRobots(''), '/anything'));
  });
});

// ── Links and sitemaps ───────────────────────────────────────────────

describe('extractProductLinks / extractListingLinks / parseSitemap', () => {
  test('product links are absolute, same-host, canonical and deduped', () => {
    const links = extractProductLinks(LISTING_PAGE, `${BASE}/porsche/996--911--1997-05/water---coolant-pumps/`);
    assert.deepEqual(links.sort(), [
      `${BASE}/p/elring-thermostat-gasket-996-turbo/`,
      `${BASE}/p/water-pump-996/`,
      `${BASE}/parts/99610601176/`,
      `${BASE}/parts/99761209005/`,
    ]);
  });

  test('pagination and category links from a listing page', () => {
    const page = `${BASE}/porsche/996--911--1997-05/water---coolant-pumps/`;
    const { pagination, categories } = extractListingLinks(LISTING_PAGE, page, { includeCategories: true });
    assert.deepEqual(pagination.sort(), [`${page}2/`, `${page}3/`]);
    assert.ok(categories.includes(`${BASE}/porsche/boxster-986-987-981/ignition-coils/`));
    assert.ok(categories.includes(`${BASE}/b/original/`));
    assert.ok(!categories.some((c) => c.includes('/p/') || c.includes('/parts/')));
    // From page 2, page 3 is pagination and page 1 is the base path.
    const p2 = extractListingLinks(LISTING_PAGE, `${page}2/`);
    assert.ok(p2.pagination.includes(`${page}3/`));
    assert.deepEqual(p2.categories, []);
  });

  test('sitemap index and urlset', () => {
    const idx = parseSitemap(SITEMAP_INDEX);
    assert.equal(idx.kind, 'index');
    assert.deepEqual(idx.locs, [`${BASE}/sitemap-pages.xml`, `${BASE}/sitemap-products.xml`]);
    const set = parseSitemap(SITEMAP_URLSET);
    assert.equal(set.kind, 'urlset');
    assert.deepEqual(set.locs, [`${BASE}/parts/99761209005/`, `${BASE}/p/elring-thermostat-gasket-996-turbo/`]);
    assert.deepEqual(parseSitemap('<html>not a sitemap</html>'), { kind: 'unknown', locs: [] });
  });

  test('decodeEntities resolves entities without creating tags', () => {
    assert.equal(decodeEntities('Water &amp; Coolant'), 'Water & Coolant');
    assert.equal(decodeEntities('&lt;p&gt;Fits 996&lt;/p&gt;'), '<p>Fits 996</p>');
    assert.equal(decodeEntities('plain'), 'plain');
  });

  test('htmlToText keeps block boundaries', () => {
    assert.equal(htmlToText('<p>One</p><p>Two</p><ul><li>A</li><li>B</li></ul>'), 'One Two A B');
  });
});

// ── CLI end to end against a local fake site ─────────────────────────
// Not a pure-function test: this spins up a local HTTP server that serves the
// fixtures above and runs the real CLI against it, writing to a temp dir. It
// proves the plumbing (robots, sitemap, crawl, output files, failure line).

type Routes = Record<string, { status?: number; body: string; type?: string }>;

async function serve(routes: (base: string) => Routes, fallbackStatus = 404) {
  let base = '';
  const server = http.createServer((req, res) => {
    const r = routes(base)[(req.url ?? '/').split('#')[0]];
    res.writeHead(r ? r.status ?? 200 : fallbackStatus, { 'Content-Type': r?.type ?? 'text/html; charset=utf-8' });
    res.end(r ? r.body : 'nope');
  });
  await new Promise<void>((ok) => server.listen(0, '127.0.0.1', ok));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return { base, close: () => new Promise<void>((ok) => server.close(() => ok())) };
}

function runCli(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  const tsx = path.join(__dirname, '..', 'node_modules', '.bin', 'tsx');
  return new Promise((resolve) => {
    execFile(tsx, [path.join(__dirname, 'harvest.ts'), ...args], { env: { ...process.env, DESIGN911_BASE_URL: '' } }, (err, stdout, stderr) => {
      const code = err ? (typeof (err as { code?: unknown }).code === 'number' ? ((err as { code: number }).code) : -1) : 0;
      resolve({ code, stdout, stderr });
    });
  });
}

describe('harvest CLI (local fake site)', () => {
  const tmpDirs: string[] = [];
  after(async () => { for (const d of tmpDirs) await fs.rm(d, { recursive: true, force: true }); });
  const tmp = async () => { const d = await fs.mkdtemp(path.join(os.tmpdir(), 'forge-harvest-')); tmpDirs.push(d); return d; };

  const rewrite = (html: string, base: string) => html.split(BASE).join(base);

  test('sitemap discovery → candidates + corpus written, products.json untouched', async () => {
    const site = await serve((b) => ({
      '/robots.txt': { body: `User-agent: *\nDisallow: /checkout/\nSitemap: ${b}/sitemap.xml\n`, type: 'text/plain' },
      '/sitemap.xml': { body: rewrite(SITEMAP_INDEX, b), type: 'application/xml' },
      '/sitemap-pages.xml': { status: 404, body: '' },
      '/sitemap-products.xml': {
        type: 'application/xml',
        body: `<urlset>${[
          '/parts/99761209005/', '/parts/92863210100/', '/parts/99610601176/', '/checkout/parts/x/',
          '/p/elring-thermostat-gasket-996-turbo/', '/p/ignition-coil-pack-boxster-986/',
        ].map((u) => `<url><loc>${b}${u}</loc></url>`).join('')}</urlset>`,
      },
      '/parts/99761209005/': { body: rewrite(BARE_PARTS_PAGE, b) },
      '/parts/92863210100/': { body: rewrite(GLOVE_BOX_PAGE, b) },
      '/parts/99610601176/': { body: rewrite(THIN_PAGE, b) },
      '/p/elring-thermostat-gasket-996-turbo/': { body: rewrite(RICH_P_PAGE, b) },
      '/p/ignition-coil-pack-boxster-986/': { body: rewrite(MICRODATA_PAGE, b) },
    }));
    try {
      const out = await tmp();
      const r = await runCli(['--base', site.base, '--find-missing', '3', '--corpus', '2', '--delay', '0', '--out-dir', out]);
      assert.equal(r.code, 0, r.stderr + r.stdout);
      assert.match(r.stdout, /discovery: 5 product URLs from sitemaps/);
      assert.match(r.stdout, /Harvest summary/);
      assert.match(r.stdout, /descriptions: missing 2, thin 1, present 2/);
      const cands = JSON.parse(await fs.readFile(path.join(out, 'products.candidates.json'), 'utf8'));
      assert.deepEqual(cands.map((c: { id: string }) => c.id), ['p01', 'p02', 'p03']);
      assert.deepEqual(new Set(cands.map((c: { partNumber: string }) => c.partNumber)), new Set(['99761209005', '92863210100', '99610601176']));
      const corpus = JSON.parse(await fs.readFile(path.join(out, 'voice-corpus.json'), 'utf8'));
      assert.equal(corpus.length, 2);
      assert.deepEqual(new Set(corpus.map((c: { category: string }) => c.category)), new Set(['Water & Coolant Pumps', 'Ignition Coils']));
      await assert.rejects(fs.access(path.join(out, 'products.json')), 'products.json must not be written without --write-products');
    } finally {
      await site.close();
    }
  });

  test('no sitemap → crawls --seed with pagination; --write-products merges and renumbers', async () => {
    const cat = '/porsche/996--911--1997-05/water---coolant-pumps/';
    const site = await serve((b) => ({
      '/robots.txt': { status: 404, body: '' },
      [cat]: { body: rewrite(LISTING_PAGE, b) },
      [`${cat}2/`]: { body: `<a href="/parts/92863210100/">x</a><a href="${cat}3/">3</a>` },
      '/parts/99761209005/': { body: rewrite(BARE_PARTS_PAGE, b) },
      '/parts/92863210100/': { body: rewrite(GLOVE_BOX_PAGE, b) },
      '/parts/99610601176/': { body: rewrite(THIN_PAGE, b) },
      '/p/elring-thermostat-gasket-996-turbo/': { body: rewrite(RICH_P_PAGE, b) },
      '/p/water-pump-996/': { body: rewrite(RICH_P_PAGE, b) },
    }));
    try {
      const out = await tmp();
      await fs.writeFile(path.join(out, 'products.json'), JSON.stringify([
        { id: 'p01', partNumber: '99761209005', manufacturer: 'Porsche (Genuine)', name: 'Battery Cable', category: 'Electrical',
          summary: 'A battery cable.', qualityTier: 'Genuine', fitment: [{ model: '997' }], descriptionStatus: 'missing' },
      ]));
      const r = await runCli(['--base', site.base, '--seed', cat, '--find-missing', '3', '--corpus', '1', '--delay', '0', '--max-pages', '30', '--out-dir', out, '--write-products']);
      assert.equal(r.code, 0, r.stderr + r.stdout);
      assert.match(r.stdout, /0 product URLs from sitemaps/);
      assert.match(r.stdout, /listing \/porsche\/996--911--1997-05\/water---coolant-pumps\/: 4 product links, 2 pagination/);
      const products = JSON.parse(await fs.readFile(path.join(out, 'products.json'), 'utf8'));
      assert.deepEqual(products.map((p: { id: string }) => p.id), ['p01', 'p02', 'p03']);
      const battery = products.find((p: { partNumber: string }) => p.partNumber === '99761209005');
      assert.equal(battery.name, 'Battery Cable', 'human name kept over generic harvested name');
      assert.equal(battery.summary, 'A battery cable.');
      assert.deepEqual(battery.fitment, [{ model: '997' }]);
      assert.match(battery.statusNote, /^Harvested from 127\.0\.0\.1/);
    } finally {
      await site.close();
    }
  });

  test('blocked host → one plain line naming host and status, nothing written, exit 1', async () => {
    const site = await serve(() => ({}), 403);
    try {
      const out = await tmp();
      const r = await runCli(['--base', site.base, '--delay', '0', '--out-dir', out]);
      assert.equal(r.code, 1);
      const lines = r.stderr.trim().split('\n');
      assert.equal(lines.length, 1, r.stderr);
      assert.match(lines[0], new RegExp(`cannot reach ${site.base.replace('http://', '').replace(/\./g, '\\.')}: returned HTTP 403`));
      assert.doesNotMatch(r.stderr, /\bat .*\.ts:\d+/, 'no stack trace');
      assert.deepEqual(await fs.readdir(out), []);
    } finally {
      await site.close();
    }
  });
});
