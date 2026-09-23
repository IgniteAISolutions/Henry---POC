// Forge — the four stages, in order: search, fetch, verify, write.
//
// Evidence mode:
//   live      — search the web and fetch pages now.
//   recorded  — replay data/evidence-fixtures.json. For rehearsals, flaky
//               venue wifi, and machines without outbound access.
//   auto      — live first; if live finds nothing confirming the part
//               number, fall back to recorded and say so.

import type { EnrichedPart, Evidence, Part, Stage, StageName } from './types';
import { searchByPartNumber } from './search';
import { harvestEvidence } from './scrape';
import { verify } from './verify';
import { writeDescription, writerConfigured } from './writer';
import { loadCorpus, loadFixtures } from './data';

export type EvidenceMode = 'live' | 'recorded' | 'auto';

export interface RunOptions {
  mode?: EvidenceMode;
  /** Write even when verification came back unconfirmed. Off by default:
   *  the point of the demo is that Forge declines to guess. */
  force?: boolean;
  onStage?: (stage: Stage) => void;
}

const STAGES: StageName[] = ['search', 'fetch', 'verify', 'write'];

/** Vercel stops the function at 60s. Finish inside 55s so the stream always
 *  ends with a result the UI can show, rather than being cut off mid-run. */
export const PIPELINE_BUDGET_MS = 55_000;
const MIN_WRITE_MS = 8_000;

export async function runPipeline(part: Part, opts: RunOptions = {}): Promise<EnrichedPart> {
  const mode = opts.mode ?? 'auto';
  const deadline = Date.now() + PIPELINE_BUDGET_MS;
  const stages: Stage[] = STAGES.map((name) => ({ name, status: 'pending' }));
  const emit = (name: StageName, patch: Partial<Stage>) => {
    const s = stages.find((x) => x.name === name)!;
    Object.assign(s, patch);
    opts.onStage?.({ ...s });
  };
  const timed = async <T,>(name: StageName, fn: () => Promise<T>): Promise<T> => {
    const t0 = Date.now();
    emit(name, { status: 'running' });
    try {
      const out = await fn();
      emit(name, { ms: Date.now() - t0 });
      return out;
    } catch (err) {
      emit(name, { status: 'failed', detail: (err as Error).message, ms: Date.now() - t0 });
      throw err;
    }
  };

  let evidence: Evidence[] = [];

  // 1 + 2. Search and fetch (live), or replay (recorded).
  if (mode !== 'recorded') {
    const found = await timed('search', () =>
      searchByPartNumber(part.partNumber, { manufacturer: part.manufacturer, name: part.name })
    );
    emit('search', { status: 'done', detail: `${found.hits.length} candidates via ${found.provider}` });

    const pages = await timed('fetch', async () => {
      const settled = await Promise.allSettled(found.hits.map((h) => harvestEvidence(h, part.partNumber)));
      return settled.flatMap((r) => (r.status === 'fulfilled' ? r.value : []));
    });
    evidence = pages;
    const confirmed = pages.filter((e) => e.partNumberConfirmed).length;
    emit('fetch', {
      status: 'done',
      detail: `${pages.length} product pages read from ${found.hits.length} results, ${confirmed} carry the part number`,
    });
  }

  const liveConfirmed = evidence.some((e) => e.partNumberConfirmed);
  if (mode === 'recorded' || (mode === 'auto' && !liveConfirmed)) {
    const recorded = (await loadFixtures())[part.partNumber] ?? [];
    if (mode === 'recorded') {
      emit('search', { status: 'skipped', detail: 'Recorded evidence mode' });
      emit('fetch', {
        status: 'done',
        detail: `${recorded.length} recorded sources replayed, ${recorded.filter((e) => e.partNumberConfirmed).length} carry the part number`,
      });
    } else if (recorded.length) {
      const prev = stages.find((s) => s.name === 'fetch')?.detail ?? '';
      emit('fetch', { status: 'done', detail: `${prev}. Live found nothing confirming, replaying ${recorded.length} recorded sources` });
    }
    evidence = [...evidence, ...recorded];
  }

  // 3. Verify.
  const verification = await timed('verify', async () => verify(evidence, part.partNumber));
  emit('verify', {
    status: 'done',
    detail: `${verification.verdict}, ${verification.confidence}% (${verification.sourcesConfirming} of ${verification.sourcesChecked} sources confirm)`,
  });

  const result: EnrichedPart = { part, evidence, verification, stages };

  // 4. Write, unless the evidence cannot carry it.
  if (verification.verdict === 'unconfirmed' && !opts.force) {
    emit('write', { status: 'skipped', detail: 'Not enough verified evidence. Forge will not guess.' });
    return result;
  }
  if (!writerConfigured()) {
    emit('write', { status: 'skipped', detail: 'OPENAI_API_KEY not set' });
    result.error = 'Set OPENAI_API_KEY in .env.local to generate descriptions.';
    return result;
  }

  const remaining = deadline - Date.now();
  if (remaining < MIN_WRITE_MS) {
    emit('write', { status: 'skipped', detail: 'Ran out of time on this request. Try Recorded mode or run it again.' });
    result.error = 'Search and reading took too long to leave time for writing.';
    return result;
  }

  try {
    const corpus = await loadCorpus();
    result.description = await timed('write', () => writeDescription(part, verification, corpus, deadline));
    emit('write', { status: 'done', detail: `${result.description.model}, $${result.description.costUsd.toFixed(4)}` });
  } catch (err) {
    result.error = (err as Error).message;
  }

  return result;
}
