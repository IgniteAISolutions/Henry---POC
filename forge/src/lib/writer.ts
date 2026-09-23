// Forge — writing the listing.
//
// OpenAI, for parity with E.V.A. Same contract E.V.A uses: a strict JSON
// response, sanitised afterwards, never trusted blindly.

import OpenAI from 'openai';
import type { Part, Evidence, Verification, GeneratedDescription } from './types';
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

// Phrases the house voice forbids. Belt and braces: the prompt bans them,
// this strips any that slip through anyway.
const BANNED = [
  /\bpremium\b/gi,
  /\bultimate\b/gi,
  /\bstate-of-the-art\b/gi,
  /\bcutting-edge\b/gi,
  /\bunrivalled\b/gi,
  /\brevolutionary\b/gi,
  /\bgame-changing\b/gi,
  /\blook no further\b/gi,
  /\brest assured\b/gi,
  /\bpeace of mind\b/gi,
  /\bunleash\b/gi,
];

function sanitise(html: string): string {
  let out = html
    .replace(/\s*[—–]\s*/g, ', ') // no em or en dashes in house copy
    .replace(/!/g, '.')
    .replace(/<(?!\/?(p|br|strong|ul|li)\b)[^>]*>/gi, ''); // allow only listing tags
  for (const re of BANNED) out = out.replace(re, '');
  // Drop any paragraph that is a placeholder the model was told never to write.
  out = out.replace(/<p>[^<]*\b(N\/A|Not specified|Unknown|TBC)\b[^<]*<\/p>/gi, '');
  return out.replace(/\s{2,}/g, ' ').replace(/ ,/g, ',').trim();
}

let client: OpenAI | null = null;
function openai(): OpenAI {
  if (!process.env.OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY is not set. Add it to .env.local to generate descriptions.');
  }
  client ??= new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  return client;
}

export function writerConfigured(): boolean {
  return Boolean(process.env.OPENAI_API_KEY);
}

export async function writeDescription(
  part: Part,
  evidence: Evidence[],
  verification: Verification,
  corpus: CorpusSample[]
): Promise<GeneratedDescription> {
  const model = process.env.OPENAI_MODEL || 'gpt-4o';
  const isReasoning = /^o\d/.test(model);

  const res = await openai().chat.completions.create({
    model,
    messages: [
      { role: 'system', content: buildSystemPrompt(corpus) },
      { role: 'user', content: buildUserMessage(part, evidence, verification) },
    ],
    response_format: { type: 'json_object' },
    // Reasoning models reject temperature. Everything else gets a low one:
    // this is catalogue copy, not creative writing.
    ...(isReasoning ? {} : { temperature: 0.3 }),
  });

  const raw = res.choices[0]?.message?.content ?? '{}';
  let parsed: { short_html?: string; meta_description?: string; long_html?: string };
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('The model returned something that was not valid JSON.');
  }

  const [inCost, outCost] = COSTS[model] ?? COSTS['gpt-4o'];
  const usage = res.usage;
  const costUsd = usage
    ? (usage.prompt_tokens * inCost + usage.completion_tokens * outCost) / 1_000_000
    : 0;

  // Trace every fact back to where it came from, so the demo can show its
  // working rather than asking the room to trust it.
  const factsUsed = [
    ...verification.corroborated.map((f) => ({ fact: f, source: 'corroborated (2+ sources)' })),
    ...verification.singleSource.map((f) => {
      const m = f.match(/^(.*) \((.+)\)$/);
      return m ? { fact: m[1], source: m[2] } : { fact: f, source: 'single source' };
    }),
  ];

  const omitted = verification.conflicts.map(
    (c) => `${c.field}: sources disagree (${c.values.map((v) => `${v.value} @ ${v.domain}`).join(' vs ')})`
  );

  return {
    shortHtml: sanitise(parsed.short_html ?? ''),
    metaDescription: (parsed.meta_description ?? '').replace(/[—–]/g, ',').trim(),
    longHtml: sanitise(parsed.long_html ?? ''),
    factsUsed,
    omitted,
    model,
    generatedAt: new Date().toISOString(),
    costUsd: Math.round(costUsd * 10000) / 10000,
  };
}
