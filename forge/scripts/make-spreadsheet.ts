// Writes the "before" catalogue spreadsheet: the 10 Design 911 parts with no
// description, one generic sentence each. Same workbook the UI serves at
// GET /api/export.
//
//   npm run spreadsheet

import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { loadParts } from '../src/lib/data';
import { catalogueWorkbook } from '../src/lib/export';

(async () => {
  const parts = await loadParts();
  const out = path.join(process.cwd(), 'deliverables', 'design911-catalogue-10-parts.xlsx');
  await writeFile(out, await catalogueWorkbook(parts));
  console.log(`Wrote ${parts.length} parts to ${path.relative(process.cwd(), out)}`);
})();
