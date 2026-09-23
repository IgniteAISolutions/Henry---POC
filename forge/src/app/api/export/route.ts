import { catalogueWorkbook, resultsWorkbook } from '@/lib/export';
import { loadParts } from '@/lib/data';
import type { EnrichedPart } from '@/lib/types';

export const dynamic = 'force-dynamic';

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const stamp = () => new Date().toISOString().slice(0, 10);

/** GET: the "before" catalogue spreadsheet. */
export async function GET() {
  const buf = await catalogueWorkbook(await loadParts());
  return new Response(new Uint8Array(buf), {
    headers: { 'Content-Type': XLSX, 'Content-Disposition': `attachment; filename="forge-catalogue-${stamp()}.xlsx"` },
  });
}

/** POST: the "after" spreadsheet, built from whatever the UI has run. */
export async function POST(req: Request) {
  const { results } = (await req.json()) as { results: EnrichedPart[] };
  const buf = await resultsWorkbook(results ?? []);
  return new Response(new Uint8Array(buf), {
    headers: { 'Content-Type': XLSX, 'Content-Disposition': `attachment; filename="forge-listings-${stamp()}.xlsx"` },
  });
}
