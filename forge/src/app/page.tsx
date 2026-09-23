'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { EnrichedPart, Part, Stage } from '@/lib/types';
import PartList from '@/components/PartList';
import PartDetail from '@/components/PartDetail';

type Mode = 'auto' | 'live' | 'recorded';

interface Meta {
  voice: { state: 'fitted' | 'reconstructed'; sampleCount: number; label: string };
  config: { writer: string | null; search: string };
}

const MODES: Array<{ id: Mode; label: string; hint: string }> = [
  { id: 'auto', label: 'Auto', hint: 'Live web first, recorded evidence if live finds nothing' },
  { id: 'live', label: 'Live', hint: 'Search and read the web now' },
  { id: 'recorded', label: 'Recorded', hint: 'Replay evidence captured on 23 Sep 2026' },
];

const emptyStages = (): Stage[] =>
  (['search', 'fetch', 'verify', 'write'] as const).map((name) => ({ name, status: 'pending' }));

async function download(res: Response, fallbackName: string) {
  const blob = await res.blob();
  const name = res.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1] ?? fallbackName;
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name });
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function Home() {
  const [parts, setParts] = useState<Part[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [results, setResults] = useState<Record<string, EnrichedPart>>({});
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('auto');
  const [batch, setBatch] = useState(false);

  useEffect(() => {
    fetch('/api/products')
      .then((r) => r.json())
      .then((d) => {
        setParts(d.parts);
        setMeta({ voice: d.voice, config: d.config });
        setSelected(d.parts[0]?.id ?? null);
      });
  }, []);

  const run = useCallback(
    async (part: Part, force = false) => {
      setRunning((s) => new Set(s).add(part.id));
      // Show the stage track immediately, before the first event arrives.
      setResults((r) => ({
        ...r,
        [part.id]: {
          part,
          evidence: [],
          stages: emptyStages(),
          verification: { verdict: 'unconfirmed', confidence: 0, sourcesChecked: 0, sourcesConfirming: 0, corroborated: [], singleSource: [], conflicts: [], notes: [] },
        },
      }));

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: part.id, mode, force }),
        });
        if (!res.body) throw new Error('No response stream');

        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let nl: number;
          while ((nl = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, nl).trim();
            buf = buf.slice(nl + 1);
            if (!line) continue;
            const msg = JSON.parse(line);
            if (msg.type === 'stage') {
              setResults((r) => {
                const cur = r[part.id];
                if (!cur) return r;
                return { ...r, [part.id]: { ...cur, stages: cur.stages.map((s) => (s.name === msg.stage.name ? msg.stage : s)) } };
              });
            } else if (msg.type === 'result') {
              setResults((r) => ({ ...r, [part.id]: msg.result }));
            } else if (msg.type === 'error') {
              setResults((r) => ({ ...r, [part.id]: { ...r[part.id], error: msg.error } }));
            }
          }
        }
      } catch (err) {
        setResults((r) => ({ ...r, [part.id]: { ...r[part.id], error: (err as Error).message } }));
      } finally {
        setRunning((s) => {
          const n = new Set(s);
          n.delete(part.id);
          return n;
        });
      }
    },
    [mode]
  );

  // One at a time, and the view follows along, so the room can watch each
  // part go through rather than ten spinners at once.
  const runAll = async () => {
    setBatch(true);
    for (const p of parts) {
      setSelected(p.id);
      await run(p);
    }
    setBatch(false);
  };

  const stats = useMemo(() => {
    const done = Object.values(results).filter((r) => r.stages.every((s) => s.status !== 'pending' && s.status !== 'running'));
    return {
      run: done.length,
      written: done.filter((r) => r.description).length,
      refused: done.filter((r) => !r.description && r.verification.verdict === 'unconfirmed').length,
      cost: done.reduce((a, r) => a + (r.description?.costUsd ?? 0), 0),
    };
  }, [results]);

  const exportResults = async () => {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: parts.map((p) => results[p.id]).filter(Boolean) }),
    });
    await download(res, 'forge-listings.xlsx');
  };

  const part = parts.find((p) => p.id === selected);

  return (
    <div className="flex min-h-screen flex-col">
      {/* ── Top bar ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 border-b border-ink-700 bg-ink-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-black tracking-[0.18em] text-chalk-50">
              FORGE<span className="text-forge-500">.</span>
            </span>
            <span className="text-sm text-chalk-400">for Design 911</span>
          </div>

          {meta && (
            <span
              title={meta.voice.label}
              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset ${
                meta.voice.state === 'fitted'
                  ? 'bg-signal-ok/10 text-signal-ok ring-signal-ok/30'
                  : 'bg-signal-warn/10 text-signal-warn ring-signal-warn/30'
              }`}
            >
              Voice: {meta.voice.state === 'fitted' ? `fitted to ${meta.voice.sampleCount} real listings` : 'reconstructed, run npm run harvest'}
            </span>
          )}

          <div className="ml-auto flex flex-wrap items-center gap-3">
            <div className="flex rounded-lg border border-ink-700 bg-ink-900 p-0.5" role="radiogroup" aria-label="Evidence mode">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  title={m.hint}
                  role="radio"
                  aria-checked={mode === m.id}
                  onClick={() => setMode(m.id)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                    mode === m.id ? 'bg-ink-700 text-chalk-50' : 'text-chalk-400 hover:text-chalk-200'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <a href="/api/export" className="rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-chalk-200 hover:border-chalk-500">
              Catalogue .xlsx
            </a>
            <button
              onClick={exportResults}
              disabled={!stats.run}
              className="rounded-lg border border-ink-600 px-3 py-2 text-xs font-semibold text-chalk-200 hover:border-chalk-500 disabled:opacity-40"
            >
              Export listings .xlsx
            </button>
            <button
              onClick={runAll}
              disabled={batch || !parts.length}
              className="rounded-lg bg-forge-500 px-4 py-2 text-xs font-bold uppercase tracking-wider text-white hover:bg-forge-600 disabled:opacity-50"
            >
              {batch ? `Running ${stats.run + 1}/${parts.length}…` : 'Run all 10'}
            </button>
          </div>
        </div>

        {meta && !meta.config.writer && (
          <div className="border-t border-signal-warn/20 bg-signal-warn/10 px-4 py-2 text-center text-xs text-signal-warn sm:px-6">
            OPENAI_API_KEY is not set. Search and verification will run; writing is skipped. Add it to <code>.env.local</code> and restart.
          </div>
        )}
      </header>

      {/* ── Body ────────────────────────────────────────────────── */}
      <main className="mx-auto grid w-full max-w-[1600px] flex-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="h-fit overflow-hidden rounded-xl border border-ink-700 bg-ink-900/80 shadow-panel lg:sticky lg:top-24">
          <div className="border-b border-ink-700 px-4 py-3">
            <p className="label">Design 911 · parts with no description</p>
            <div className="mt-2 grid grid-cols-3 gap-2 text-center">
              {[
                ['Run', `${stats.run}/${parts.length}`],
                ['Written', String(stats.written)],
                ['Refused', String(stats.refused)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md bg-ink-850 py-1.5">
                  <div className="font-mono text-lg font-semibold tabular-nums text-chalk-50">{v}</div>
                  <div className="text-[10px] uppercase tracking-wider text-chalk-500">{k}</div>
                </div>
              ))}
            </div>
            {stats.cost > 0 && (
              <p className="mt-2 text-right font-mono text-[11px] text-chalk-500">Model cost so far ${stats.cost.toFixed(4)}</p>
            )}
          </div>
          <PartList parts={parts} results={results} running={running} selected={selected} onSelect={setSelected} />
        </aside>

        <section className="min-w-0">
          {part ? (
            <PartDetail
              part={part}
              result={results[part.id]}
              running={running.has(part.id)}
              onRun={() => run(part)}
              onForce={() => run(part, true)}
            />
          ) : (
            <p className="text-chalk-400">Loading catalogue…</p>
          )}
        </section>
      </main>

      <footer className="border-t border-ink-700 px-6 py-4 text-center text-[11px] text-chalk-500">
        Forge · a demonstration by IgniteAI Solutions. Not affiliated with or endorsed by Porsche AG or Design 911.
      </footer>
    </div>
  );
}
