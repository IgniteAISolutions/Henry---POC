// Forge — writing the listing.
//
// OpenAI, for parity with E.V.A. The model returns strict JSON, which is then
// sanitised: the output is rendered as HTML in the UI and exported to the
// product admin, so it is treated as untrusted.

import OpenAI from 'openai';
import type { Part, Verification, GeneratedDescription } from './types';
import { buildSystemPrompt, buildUserMessage, type CorpusSample } from './voice';

// USD per 1M tokens (input, output). Mirrors E.V.A's cost table.
const COSTS: Record<string, [number, number]> = {
  'gpt-4o-mini': [0.15, 0.6],
  'gpt-4o': [2.5, 10.0],
  'gpt-4.1': [2.0, 8.0],
  'gpt-4.1-mini': [0.4, 1.6],
  o3: [10.0, 40.0],
  'o3-mini': [1.1, 4.4],
};

/** The house-voice ban list. Must match the list in the system prompt. */
export const BANNED_PHRASES = [
  'premium', 'ultimate', 'perfect', 'cutting-edge', 'state-of-the-art', 'unrivalled', 'unrivaled',
  'revolutionary', 'game-changing', 'look no further', 'rest assured', 'peace of mind',
  'elevate', 'elevates', 'unleash', 'transform your driving experience',
];

export function findBanned(text: string): string[] {
  const plain = text.replace(/<[^>]+>/g, ' ');
  return BANNED_PHRASES.filter((p) => new RegExp(`\\b${p.replace(/[-\s]/g, '[-\\s]')}\\b`, 'i').test(plain));
}

const ALLOWED = /^(p|br|strong|ul|li)$/i;
const PLACEHOLDER_LINE = /^\s*[^:<>]{1,60}:\s*(N\/A|Not specified|Unknown|TBC|None)\.?\s*$/i;

/** Shared text rules: house punctuation, keeping numeric ranges intact. */
function houseText(s: string): string {
  return s
    .replace(/\b((?:19|20)\d{2})\s*–\s*((?:19|20)?\d{2})\b/g, '$1-$2') // 1997 – 99 is a year range
    .replace(/(\d)–(\d)/g, '$1-$2') // tight en dash between digits is a range
    .replace(/\s*[—–]\s*/g, ', ') // no other em or en dashes
    .replace(/!/g, '.');
}

export function sanitise(html: string): string {
  // Whole blocks whose contents must never render as text.
  let out = html
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<\s*(script|style|iframe|noscript|template)\b[\s\S]*?<\s*\/\s*\1\s*>/gi, '');

  // Tags: allowed ones are rebuilt bare (no attributes, so no handlers or
  // styles survive); everything else that looks like a tag is removed.
  // "< 25 Nm" is not a tag and is left alone.
  out = out.replace(/<\s*(\/?)\s*([a-zA-Z][\w-]*)\b[^<>]*>/g, (_, slash: string, name: string) =>
    ALLOWED.test(name) ? `<${slash}${name.toLowerCase()}>` : ''
  );

  // Placeholders the model was told never to write: only "Label: N/A"-shaped
  // lines, so prose like "if the history is unknown" is untouched.
  out = out.replace(/<p>([\s\S]*?)<\/p>/g, (_, inner: string) => {
    const kept = inner.split(/<br>/).filter((seg) => !PLACEHOLDER_LINE.test(seg.replace(/<[^>]+>/g, '')));
    const body = kept.join('<br>').trim();
    return body ? `<p>${body}</p>` : '';
  });

  return houseText(out).replace(/[ \t]{2,}/g, ' ').replace(/ ,/g, ',').trim();
}

export function sanitiseText(s: string): string {
  return houseText(s).replace(/<[^>]*>/g, '').replace(/\s{2,}/g, ' ').trim();
}

let client: OpenAI | null = null;
function openai(): OpenAI {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY is not set. Add it to .env.local (or Vercel env vars) to generate descriptions.');
  }
  client ??= new OpenAI({ apiKey: process.env.OPENAI_API_KEY, maxRetries: 0 });
  return client;
}

export function writerConfigured(): boolean {
  return Boolean(process.env.OPENAI_API_KEY);
}

interface Draft {
  short_html?: string;
  meta_description?: string;
  long_html?: string;
}

export async function writeDescription(
  part: Part,
  verification: Verification,
  corpus: CorpusSample[],
  deadline = Date.now() + 30_000
): Promise<GeneratedDescription> {
  const model = process.env.OPENAI_MODEL || 'gpt-4o';
  const isReasoning = /^o\d/.test(model);
  const [inCost, outCost] = COSTS[model] ?? COSTS['gpt-4o'];
  let costUsd = 0;

  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: 'system', content: buildSystemPrompt(corpus) },
    { role: 'user', content: buildUserMessage(part, verification) },
  ];

  const ask = async (): Promise<{ draft: Draft; raw: string }> => {
    const timeout = Math.max(5_000, Math.min(30_000, deadline - Date.now() - 2_000));
    const res = await openai().chat.completions.create(
      {
        model,
        messages,
        response_format: { type: 'json_object' },
        // Reasoning models reject temperature. Catalogue copy wants a low one.
        ...(isReasoning ? {} : { temperature: 0.3 }),
      },
      { timeout }
    );
    if (res.usage) costUsd += (res.usage.prompt_tokens * inCost + res.usage.completion_tokens * outCost) / 1_000_000;
    const raw = res.choices[0]?.message?.content ?? '{}';
    try {
      return { draft: JSON.parse(raw) as Draft, raw };
    } catch {
      throw new Error('The model returned something that was not valid JSON.');
    }
  };

  let { draft, raw } = await ask();
  const all = (d: Draft) => [d.short_html, d.meta_description, d.long_html].filter(Boolean).join(' ');

  // One corrective rewrite when banned phrasing slips through, time allowing.
  // Deleting the words instead leaves broken sentences ("A -grade seal").
  let banned = findBanned(all(draft));
  if (banned.length && deadline - Date.now() > 12_000) {
    messages.push(
      { role: 'assistant', content: raw },
      {
        role: 'user',
        content: `Rewrite without these words or phrases: ${banned.join(', ')}. Change nothing else. Return the same JSON shape.`,
      }
    );
    ({ draft } = await ask());
    banned = findBanned(all(draft));
  }

  const factsUsed = [
    ...verification.accepted.attributes.map((a) => ({ fact: `${a.label}: ${a.value}`, source: a.sources.join(', ') })),
    ...verification.accepted.fitment.map((f) => ({ fact: `Fits ${f.vehicle}`, source: f.sources.join(', ') })),
    ...verification.accepted.oeReferences.map((r) => ({ fact: `OE ${r.ref}`, source: r.sources.join(', ') })),
  ];

  return {
    shortHtml: sanitise(draft.short_html ?? ''),
    metaDescription: sanitiseText(draft.meta_description ?? ''),
    longHtml: sanitise(draft.long_html ?? ''),
    factsUsed,
    omitted: verification.conflicts.map(
      (c) => `${c.field}: sources disagree (${c.values.map((v) => `${v.value} @ ${v.domain}`).join(' vs ')})`
    ),
    warnings: banned.map((b) => `Banned phrase still present after rewrite: "${b}"`),
    model,
    generatedAt: new Date().toISOString(),
    costUsd: Math.round(costUsd * 10000) / 10000,
  };
}
