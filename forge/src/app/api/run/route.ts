// Runs the pipeline for one part and streams progress as NDJSON:
//   {"type":"stage", ...}   one per stage transition
//   {"type":"result", ...}  the finished EnrichedPart
//   {"type":"error", ...}   if the run itself blew up

import { findPart } from '@/lib/data';
import { runPipeline, type EvidenceMode } from '@/lib/pipeline';

export const dynamic = 'force-dynamic';
export const maxDuration = 60; // Vercel: live fetch + generation can take a while

export async function POST(req: Request) {
  const { id, mode = 'auto', force = false } = (await req.json()) as {
    id: string;
    mode?: EvidenceMode;
    force?: boolean;
  };

  if (!['auto', 'live', 'recorded'].includes(mode)) {
    return Response.json({ error: `Unknown mode "${mode}". Use auto, live or recorded.` }, { status: 400 });
  }

  const part = await findPart(id);
  if (!part) return Response.json({ error: `No part with id ${id}` }, { status: 404 });

  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (obj: unknown) => controller.enqueue(enc.encode(JSON.stringify(obj) + '\n'));
      try {
        const result = await runPipeline(part, {
          mode,
          force,
          onStage: (stage) => send({ type: 'stage', stage }),
        });
        send({ type: 'result', result });
      } catch (err) {
        send({ type: 'error', error: (err as Error).message });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: { 'Content-Type': 'application/x-ndjson; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}
