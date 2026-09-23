// Forge — loading the catalogue, the recorded evidence and the voice corpus.
// Plain JSON files in /data, so the whole demo state is inspectable and
// editable without a database.

import { readFile } from 'node:fs/promises';
import path from 'node:path';
import type { Evidence, Part } from './types';
import type { CorpusSample } from './voice';

const DATA = path.join(process.cwd(), 'data');

async function readJson<T>(file: string, fallback: T): Promise<T> {
  try {
    return JSON.parse(await readFile(path.join(DATA, file), 'utf8')) as T;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return fallback;
    throw err;
  }
}

export const loadParts = () => readJson<Part[]>('products.json', []);
export const loadCorpus = () => readJson<CorpusSample[]>('voice-corpus.json', []);
export const loadFixtures = () => readJson<Record<string, Evidence[]>>('evidence-fixtures.json', {});

export async function findPart(id: string): Promise<Part | undefined> {
  return (await loadParts()).find((p) => p.id === id);
}
