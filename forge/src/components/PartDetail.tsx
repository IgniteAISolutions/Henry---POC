'use client';

import type { EnrichedPart, Part, Stage } from '@/lib/types';
import { Chip, Panel, StageIcon, VerdictBadge } from './ui';
import { dealerName, sourceTier, TIER_RANK } from '@/lib/sources';

const STAGE_LABEL: Record<Stage['name'], string> = {
  search: 'Search by part number',
  fetch: 'Read the pages',
  verify: 'Cross-check sources',
  write: 'Write in house voice',
};

function StageTrack({ stages }: { stages: Stage[] }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-4">
      {stages.map((s, i) => (
        <li key={s.name} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
          <div className="flex items-center gap-2">
            <StageIcon status={s.status} />
            <span className="label !text-chalk-400">{String(i + 1).padStart(2, '0')}</span>
          </div>
          <p className="mt-2 text-sm font-medium text-chalk-50">{STAGE_LABEL[s.name]}</p>
          <p className="mt-1 min-h-[2.5em] text-xs leading-snug text-chalk-400">
            {s.detail ?? (s.status === 'pending' ? 'Waiting' : '')}
            {s.ms != null && s.status === 'done' ? <span className="text-chalk-500"> · {(s.ms / 1000).toFixed(1)}s</span> : null}
          </p>
        </li>
      ))}
    </ol>
  );
}

function Evidence({ r }: { r: EnrichedPart }) {
  const sorted = [...r.evidence].sort(
    (a, b) =>
      Number(b.partNumberConfirmed) - Number(a.partNumberConfirmed) ||
      TIER_RANK[sourceTier(a.domain)] - TIER_RANK[sourceTier(b.domain)]
  );
  const hasLive = r.evidence.some((e) => e.origin === 'live');
  const hasRecorded = r.evidence.some((e) => e.origin === 'recorded');
  const originChip = hasLive && hasRecorded
    ? <Chip tone="warn">Live + recorded</Chip>
    : hasRecorded
      ? <Chip tone="warn">Recorded evidence</Chip>
      : hasLive
        ? <Chip tone="ok">Live</Chip>
        : null;
  return (
    <Panel
      title={`Sources · ${r.verification.sourcesConfirming} of ${r.evidence.length} carry the part number`}
      aside={originChip}
    >
      <ul className="space-y-2.5">
        {sorted.map((e, i) => (
          <li
            key={i}
            className={`rounded-lg border p-3 ${
              e.partNumberConfirmed ? 'border-ink-700 bg-ink-850' : 'border-dashed border-ink-700 bg-transparent opacity-70'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-chalk-50">{e.domain}</span>
              {sourceTier(e.domain) === 'authorised' && <Chip tone="dealer">Porsche dealer · {dealerName(e.domain)}</Chip>}
              <span className={`text-[10px] font-semibold uppercase tracking-wider ${e.origin === 'live' ? 'text-signal-ok' : 'text-signal-warn'}`}>
                {e.origin === 'live' ? 'live' : 'recorded'}
              </span>
              {e.partNumberConfirmed ? (
                <Chip tone="ok">Part number on page</Chip>
              ) : (
                <Chip tone={e.note?.startsWith('Rejected') ? 'bad' : 'neutral'}>
                  {e.note?.startsWith('Rejected') ? 'Rejected' : 'Not counted'}
                </Chip>
              )}
            </div>
            <p className="mt-1.5 text-sm leading-snug text-chalk-200">
              {e.url.startsWith('http') ? (
                <a href={e.url} target="_blank" rel="noreferrer" className="hover:text-forge-400 hover:underline">
                  {e.title}
                </a>
              ) : (
                e.title
              )}
            </p>
            {e.note && !e.partNumberConfirmed && <p className="mt-1 text-xs text-chalk-500">{e.note}</p>}
          </li>
        ))}
        {!sorted.length && <li className="text-sm text-chalk-400">No pages found for this part number.</li>}
      </ul>
    </Panel>
  );
}

function Facts({ r }: { r: EnrichedPart }) {
  const v = r.verification;
  const pretty = (s: string) => {
    const i = s.indexOf('=');
    const [k, v] = [s.slice(0, i), s.slice(i + 1)];
    if (k === 'fitment') return `Fits ${v}`;
    if (k === 'oeReference') return `OE ref: ${v}`;
    return `${k}: ${v}`;
  };
  return (
    <Panel title="What Forge can stand behind" aside={<VerdictBadge verdict={v.verdict} />}>
      <div className="mb-4 flex items-end gap-3">
        <span className="font-mono text-4xl font-semibold tabular-nums text-chalk-50">{v.confidence}%</span>
        <span className="pb-1.5 text-sm text-chalk-400">confidence these facts describe this exact part</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            v.verdict === 'verified' ? 'bg-signal-ok' : v.verdict === 'unconfirmed' ? 'bg-chalk-500' : v.verdict === 'probable' ? 'bg-signal-warn' : 'bg-forge-500'
          }`}
          style={{ width: `${v.confidence}%` }}
        />
      </div>

      <dl className="mt-5 space-y-4 text-sm">
        {v.corroborated.length > 0 && (
          <div>
            <dt className="label mb-1.5">Two or more sources agree</dt>
            <dd className="flex flex-wrap gap-1.5">{v.corroborated.map((f) => <Chip key={f} tone="ok">{pretty(f)}</Chip>)}</dd>
          </div>
        )}
        {v.singleSource.length > 0 && (
          <div>
            <dt className="label mb-1.5">One source only (used, flagged)</dt>
            <dd className="flex flex-wrap gap-1.5">{v.singleSource.map((f) => <Chip key={f} tone="warn">{pretty(f)}</Chip>)}</dd>
          </div>
        )}
        {v.overrides.length > 0 && (
          <div>
            <dt className="label mb-1.5 !text-signal-info">Authorised dealer overruled another source</dt>
            <dd className="space-y-1.5">
              {v.overrides.map((o) => (
                <div key={o.field} className="rounded-md border border-signal-info/30 bg-signal-info/5 px-3 py-2 text-chalk-200">
                  <span className="font-semibold text-signal-info">{o.kind === 'fitment-detail' ? `Fitment detail, ${o.field}` : o.field}: </span>
                  kept &quot;{o.kept.value}&quot; ({o.kept.domains.map((d) => dealerName(d) ?? d).join(', ')}) over{' '}
                  {o.overruled.map((x) => `"${x.value}" (${x.domain})`).join(', ')}
                </div>
              ))}
            </dd>
          </div>
        )}
        {v.conflicts.length > 0 && (
          <div>
            <dt className="label mb-1.5 !text-forge-400">Sources disagree, left out of the copy</dt>
            <dd className="space-y-1.5">
              {v.conflicts.map((c) => (
                <div key={c.field} className="rounded-md border border-forge-500/30 bg-forge-500/5 px-3 py-2 text-chalk-200">
                  <span className="font-semibold text-forge-400">{c.kind === 'fitment-detail' ? `Fitment detail, ${c.field}` : c.field}: </span>
                  {c.values.map((x) => `"${x.value}" (${x.domain})`).join(' vs ')}
                </div>
              ))}
            </dd>
          </div>
        )}
        {v.notes.filter((n) => !n.includes('disagree') && !n.includes('kept over')).map((n) => (
          <p key={n} className="text-xs text-chalk-500">{n}</p>
        ))}
      </dl>
    </Panel>
  );
}

function Listing({ part, r, onForce, forcing }: { part: Part; r?: EnrichedPart; onForce: () => void; forcing: boolean }) {
  const d = r?.description;
  const writeStage = r?.stages.find((s) => s.name === 'write');
  const failed = r?.incomplete && r.error;
  const refused = !r?.incomplete && writeStage?.status === 'skipped' && r?.verification.verdict === 'unconfirmed';
  const confirmedButEmpty = (r?.verification.sourcesConfirming ?? 0) > 0;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Panel title="Before · on Design 911 today">
        <p className="font-mono text-xs text-chalk-500">Original Porsche Part - {part.partNumber}</p>
        <p className="mt-3 text-base text-chalk-200">{part.summary}</p>
        <p className="mt-4 text-xs text-chalk-500">
          No product description. {(part as Part & { statusNote?: string }).statusNote}
        </p>
      </Panel>

      <Panel
        title="After · written by Forge"
        aside={d ? <span className="font-mono text-[11px] text-chalk-500">{d.model} · ${d.costUsd.toFixed(4)}</span> : null}
        className={d ? 'ring-1 ring-forge-500/40' : ''}
      >
        {d ? (
          <article>
            <h4 className="text-xl font-semibold tracking-tight text-chalk-50">{part.name}</h4>
            <p className="mt-1 font-mono text-xs text-chalk-500">Part no. {part.partNumber} · {part.manufacturer}</p>
            <div className="listing mt-3 border-l-2 border-forge-500/60 pl-4 text-[13px]" dangerouslySetInnerHTML={{ __html: d.shortHtml }} />
            <div className="listing mt-5 text-[15px]" dangerouslySetInnerHTML={{ __html: d.longHtml }} />
            <div className="mt-5 rounded-lg border border-ink-700 bg-ink-850 p-3">
              <p className="label mb-1">Meta description · {d.metaDescription.length} chars</p>
              <p className="text-sm text-chalk-200">{d.metaDescription}</p>
            </div>
            {d.warnings.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-signal-warn">
                {d.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            )}
          </article>
        ) : failed ? (
          <div>
            <p className="text-lg font-medium text-forge-400">This run didn&apos;t finish.</p>
            <p className="mt-2 text-sm leading-relaxed text-chalk-400">{r?.error}</p>
          </div>
        ) : refused ? (
          <div>
            <p className="text-lg font-medium text-chalk-50">Forge won&apos;t write this one.</p>
            <p className="mt-2 text-sm leading-relaxed text-chalk-400">
              {confirmedButEmpty
                ? 'Pages carry this part number, but Forge could not pull usable facts from them.'
                : 'None of the pages Forge found carries this exact part number with usable detail.'}{' '}
              Anything written now would be a guess, and a guessed parts listing is how the wrong part gets ordered.
            </p>
            <button
              onClick={onForce}
              disabled={forcing}
              className="mt-4 rounded-md border border-ink-600 px-3 py-1.5 text-xs text-chalk-400 hover:border-chalk-500 hover:text-chalk-200 disabled:opacity-50"
            >
              {forcing ? 'Writing…' : 'Write from catalogue data only'}
            </button>
          </div>
        ) : r?.error ? (
          <p className="text-sm text-forge-400">{r.error}</p>
        ) : (
          <p className="text-sm text-chalk-500">Run Forge on this part to write the listing.</p>
        )}
      </Panel>
    </div>
  );
}

export default function PartDetail({ part, result, running, onRun, onForce }: {
  part: Part;
  result?: EnrichedPart;
  running: boolean;
  onRun: () => void;
  onForce: () => void;
}) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label">{part.category} · {part.manufacturer}</p>
          <h2 className="mt-1 text-3xl font-semibold tracking-tight text-chalk-50">{part.name}</h2>
          <p className="mt-1 font-mono text-lg text-forge-400">{part.partNumber}</p>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="rounded-lg bg-forge-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-forge-500/20 transition hover:bg-forge-600 disabled:cursor-wait disabled:opacity-60"
        >
          {running ? 'Running…' : result ? 'Run again' : 'Run Forge on this part'}
        </button>
      </div>

      {result && <StageTrack stages={result.stages} />}

      <Listing part={part} r={result} onForce={onForce} forcing={running} />

      {result && !result.incomplete && (
        <div className="grid gap-4 xl:grid-cols-2">
          <Facts r={result} />
          <Evidence r={result} />
        </div>
      )}
    </div>
  );
}
