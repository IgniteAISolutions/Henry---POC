import { NextResponse } from 'next/server';
import { loadCorpus, loadParts } from '@/lib/data';
import { voiceProvenance } from '@/lib/voice';
import { writerConfigured } from '@/lib/writer';

export const dynamic = 'force-dynamic';

export async function GET() {
  const [parts, corpus] = await Promise.all([loadParts(), loadCorpus()]);
  return NextResponse.json({
    parts,
    voice: voiceProvenance(corpus),
    config: {
      writer: writerConfigured() ? process.env.OPENAI_MODEL || 'gpt-4o' : null,
      search: process.env.GOOGLE_API_KEY && process.env.GOOGLE_CSE_ID
        ? 'google'
        : process.env.BRAVE_API_KEY
          ? 'brave'
          : 'direct',
    },
  });
}
