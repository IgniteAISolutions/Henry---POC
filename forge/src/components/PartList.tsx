'use client';

import type { EnrichedPart, Part } from '@/lib/types';
import { VerdictBadge } from './ui';

interface Props {
  parts: Part[];
  results: Record<string, EnrichedPart>;
  running: Set<string>;
  selected: string | null;
  onSelect: (id: string) => void;
}

export default function PartList({ parts, results, running, selected, onSelect }: Props) {
  return (
    <ol className="divide-y divide-ink-700/70">
      {parts.map((p, i) => {
        const r = results[p.id];
        const isRunning = running.has(p.id);
        const active = selected === p.id;
        const written = Boolean(r?.description);
        return (
          <li key={p.id}>
            <button
              onClick={() => onSelect(p.id)}
              className={`group relative flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors ${
                active ? 'bg-ink-800' : 'hover:bg-ink-850'
              } ${isRunning ? 'sweep' : ''}`}
            >
              {active && <span className="absolute inset-y-0 left-0 w-[3px] bg-forge-500" />}
              <span className="mt-0.5 w-5 shrink-0 font-mono text-xs text-chalk-500">{String(i + 1).padStart(2, '0')}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-[13px] text-chalk-50">{p.partNumber}</span>
                <span className="mt-0.5 block truncate text-sm text-chalk-400">{p.name}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1.5">
                {isRunning ? (
                  <span className="text-[11px] font-semibold text-forge-400">Running…</span>
                ) : r ? (
                  <VerdictBadge verdict={r.verification.verdict} />
                ) : (
                  <span className="rounded-full px-2 py-0.5 text-[11px] text-chalk-500 ring-1 ring-inset ring-ink-600">
                    No description
                  </span>
                )}
                {written && <span className="text-[10.5px] font-medium text-signal-ok">Listing written</span>}
                {r && !written && !isRunning && (
                  <span className="text-[10.5px] text-chalk-500">Not written</span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
