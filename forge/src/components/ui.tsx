import type { StageStatus, VerificationVerdict } from '@/lib/types';

export const VERDICT: Record<VerificationVerdict, { label: string; cls: string; dot: string }> = {
  verified: { label: 'Verified', cls: 'bg-signal-ok/15 text-signal-ok ring-signal-ok/30', dot: 'bg-signal-ok' },
  probable: { label: 'Probable', cls: 'bg-signal-warn/15 text-signal-warn ring-signal-warn/30', dot: 'bg-signal-warn' },
  conflicting: { label: 'Conflicting', cls: 'bg-forge-500/15 text-forge-400 ring-forge-500/30', dot: 'bg-forge-500' },
  unconfirmed: { label: 'Unconfirmed', cls: 'bg-ink-700 text-chalk-400 ring-ink-600', dot: 'bg-chalk-500' },
};

export function VerdictBadge({ verdict, size = 'sm' }: { verdict: VerificationVerdict; size?: 'sm' | 'lg' }) {
  const v = VERDICT[verdict];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full ring-1 ring-inset font-semibold ${v.cls} ${
        size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-[11px]'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${v.dot}`} />
      {v.label}
    </span>
  );
}

export function StageIcon({ status }: { status: StageStatus }) {
  const base = 'flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold';
  switch (status) {
    case 'done':
      return <span className={`${base} bg-signal-ok/20 text-signal-ok`}>✓</span>;
    case 'running':
      return <span className={`${base} bg-forge-500/25 ring-2 ring-forge-500/60 animate-pulse`} />;
    case 'failed':
      return <span className={`${base} bg-forge-500/25 text-forge-400`}>✕</span>;
    case 'skipped':
      return <span className={`${base} bg-ink-700 text-chalk-500`}>–</span>;
    default:
      return <span className={`${base} ring-1 ring-ink-600`} />;
  }
}

export function Chip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'ok' | 'warn' | 'bad' | 'neutral' | 'dealer' }) {
  const cls = {
    ok: 'border-signal-ok/30 bg-signal-ok/10 text-signal-ok',
    warn: 'border-signal-warn/30 bg-signal-warn/10 text-signal-warn',
    bad: 'border-forge-500/40 bg-forge-500/10 text-forge-400',
    neutral: 'border-ink-600 bg-ink-800 text-chalk-200',
    dealer: 'border-signal-info/40 bg-signal-info/10 text-signal-info',
  }[tone];
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs ${cls}`}>{children}</span>;
}

export function Panel({ title, aside, children, className = '' }: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-ink-700 bg-ink-900/80 shadow-panel backdrop-blur ${className}`}>
      <header className="flex items-center justify-between gap-3 border-b border-ink-700 px-5 py-3">
        <h3 className="label">{title}</h3>
        {aside}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}
