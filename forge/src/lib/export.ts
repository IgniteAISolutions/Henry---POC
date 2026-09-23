// Forge — spreadsheets in and out.
//
// Two workbooks:
//   catalogue — the "before" state: 10 parts, one generic sentence each.
//   results   — the "after" state: verified facts plus finished copy, laid
//               out so someone can paste straight into the product admin.

import ExcelJS from 'exceljs';
import type { EnrichedPart, Part } from './types';

const INK = 'FF0E1013';
const RED = 'FFE4342B';

function htmlToText(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>\s*<p>/gi, '\n\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&amp;/g, '&')
    .trim();
}

function styleSheet(ws: ExcelJS.Worksheet, wrapCols: string[] = []) {
  const header = ws.getRow(1);
  header.height = 28;
  header.eachCell((cell) => {
    cell.font = { bold: true, color: { argb: 'FFFFFFFF' }, size: 11 };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: INK } };
    cell.alignment = { vertical: 'middle', horizontal: 'left', wrapText: true };
    cell.border = { bottom: { style: 'medium', color: { argb: RED } } };
  });
  ws.views = [{ state: 'frozen', ySplit: 1 }];
  ws.eachRow((row, n) => {
    if (n === 1) return;
    row.alignment = { vertical: 'top', wrapText: false };
    for (const key of wrapCols) row.getCell(key).alignment = { vertical: 'top', wrapText: true };
  });
  ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: ws.columnCount } };
}

export async function catalogueWorkbook(parts: Part[]): Promise<Buffer> {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'Forge';
  const ws = wb.addWorksheet('Catalogue (before)');
  ws.columns = [
    { header: '#', key: 'n', width: 5 },
    { header: 'Part number', key: 'pn', width: 18 },
    { header: 'Manufacturer', key: 'mfr', width: 18 },
    { header: 'Product name', key: 'name', width: 30 },
    { header: 'Category', key: 'cat', width: 18 },
    { header: 'What it is (one sentence)', key: 'summary', width: 60 },
    { header: 'Headline fitment', key: 'fit', width: 30 },
    { header: 'Design 911 description', key: 'status', width: 22 },
    { header: 'Status note', key: 'note', width: 45 },
    { header: 'Design 911 URL', key: 'url', width: 48 },
  ];
  parts.forEach((p, i) =>
    ws.addRow({
      n: i + 1,
      pn: p.partNumber,
      mfr: p.manufacturer,
      name: p.name,
      cat: p.category,
      summary: p.summary,
      fit: p.fitment?.map((f) => [f.model, f.years].filter(Boolean).join(' ')).join(', ') ?? '',
      status: p.descriptionStatus === 'missing' ? 'Missing' : p.descriptionStatus,
      note: (p as Part & { statusNote?: string }).statusNote ?? '',
      url: p.sourceUrl ? { text: p.sourceUrl, hyperlink: p.sourceUrl } : '',
    })
  );
  styleSheet(ws, ['summary', 'note']);
  return Buffer.from(await wb.xlsx.writeBuffer());
}

export async function resultsWorkbook(results: EnrichedPart[]): Promise<Buffer> {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'Forge';

  const ws = wb.addWorksheet('Listings (after)');
  ws.columns = [
    { header: 'Part number', key: 'pn', width: 18 },
    { header: 'Product name', key: 'name', width: 28 },
    { header: 'Verdict', key: 'verdict', width: 13 },
    { header: 'Confidence', key: 'conf', width: 11 },
    { header: 'Sources confirming', key: 'src', width: 12 },
    { header: 'Short description (HTML)', key: 'short', width: 45 },
    { header: 'Meta description', key: 'meta', width: 50 },
    { header: 'Full description (HTML)', key: 'long', width: 70 },
    { header: 'Full description (plain text)', key: 'plain', width: 70 },
    { header: 'Left out, and why', key: 'omitted', width: 45 },
    { header: 'Model', key: 'model', width: 12 },
    { header: 'Cost (USD)', key: 'cost', width: 10 },
  ];
  for (const r of results) {
    const d = r.description;
    const row = ws.addRow({
      pn: r.part.partNumber,
      name: r.part.name,
      verdict: r.verification.verdict,
      conf: r.verification.confidence / 100,
      src: `${r.verification.sourcesConfirming}/${r.verification.sourcesChecked}`,
      short: d?.shortHtml ?? '',
      meta: d?.metaDescription ?? '',
      long: d?.longHtml ?? (r.stages.find((s) => s.name === 'write')?.detail ?? ''),
      plain: d ? htmlToText(d.longHtml) : '',
      omitted: [...(d?.omitted ?? []), ...r.verification.conflicts.map((c) => `${c.field}: sources disagree`)]
        .filter((v, i, a) => a.indexOf(v) === i)
        .join('\n'),
      model: d?.model ?? '',
      cost: d?.costUsd ?? '',
    });
    row.getCell('conf').numFmt = '0%';
    const fill = { verified: 'FF1F4D2B', probable: 'FF4D3F12', conflicting: 'FF5A1D1A', unconfirmed: 'FF33363D' }[
      r.verification.verdict
    ];
    row.getCell('verdict').fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: fill } };
    row.getCell('verdict').font = { color: { argb: 'FFFFFFFF' }, bold: true };
  }
  styleSheet(ws, ['short', 'meta', 'long', 'plain', 'omitted']);

  const ev = wb.addWorksheet('Evidence');
  ev.columns = [
    { header: 'Part number', key: 'pn', width: 18 },
    { header: 'Source', key: 'domain', width: 26 },
    { header: 'Carries part number', key: 'ok', width: 12 },
    { header: 'Origin', key: 'origin', width: 10 },
    { header: 'Page title', key: 'title', width: 70 },
    { header: 'Note', key: 'note', width: 50 },
    { header: 'URL', key: 'url', width: 60 },
  ];
  for (const r of results)
    for (const e of r.evidence)
      ev.addRow({
        pn: r.part.partNumber,
        domain: e.domain,
        ok: e.partNumberConfirmed ? 'Yes' : 'No',
        origin: e.origin,
        title: e.title,
        note: e.note ?? '',
        url: e.url.startsWith('http') ? { text: e.url, hyperlink: e.url } : e.url,
      });
  styleSheet(ev, ['title', 'note']);

  return Buffer.from(await wb.xlsx.writeBuffer());
}
