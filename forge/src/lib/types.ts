// Forge — shared domain types.
//
// The unit of work is a Part: something Design 911 sells that has a part
// number and, right now, no description worth publishing.

export type QualityTier = 'Genuine' | 'OEM' | 'OE Match' | 'Aftermarket' | 'Unknown';

export type DescriptionStatus = 'missing' | 'thin' | 'present';

/** One vehicle this part fits. Design 911 lists these explicitly, always. */
export interface Fitment {
  model: string;        // "911 (996)"
  engine?: string;      // "3.4L"
  years?: string;       // "1997-2001"
}

/** A part as it exists on the Design 911 catalogue today. */
export interface Part {
  id: string;
  partNumber: string;
  manufacturer: string;
  name: string;
  category: string;
  /** One generic sentence on what the product is. Deliberately shallow — this
   *  is the "before" state the demo improves on. */
  summary: string;
  price?: string;
  sourceUrl?: string;
  descriptionStatus: DescriptionStatus;
  existingDescription?: string;
  fitment?: Fitment[];
  qualityTier?: QualityTier;
}

/** A single piece of evidence pulled from somewhere other than Design 911. */
export interface Evidence {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  /** Did the part number actually appear in the fetched page? The difference
   *  between "a search engine thinks this is relevant" and "this page is about
   *  this exact part". */
  partNumberConfirmed: boolean;
  fields: EvidenceFields;
  fetchedAt: string;
  /** live = fetched during this run. recorded = replayed from
   *  data/evidence-fixtures.json. The UI never lets these look the same. */
  origin: 'live' | 'recorded';
  note?: string;
}

/** Facts lifted from an evidence page. Every field is optional: Forge never
 *  invents one to fill a gap. */
export interface EvidenceFields {
  oeReferences?: string[];
  fitment?: Fitment[];
  material?: string;
  dimensions?: string;
  weight?: string;
  position?: string;      // "Front", "Rear axle", "Left"
  quantityRequired?: string;
  specs?: Record<string, string>;
  bullets?: string[];
}

export type VerificationVerdict = 'verified' | 'probable' | 'unconfirmed' | 'conflicting';

export interface Verification {
  verdict: VerificationVerdict;
  /** 0-100. Confidence that the enriched facts describe THIS part number. */
  confidence: number;
  sourcesChecked: number;
  sourcesConfirming: number;
  /** Facts that appear in more than one independent source. */
  corroborated: string[];
  /** Facts that appear in exactly one source. Usable, but flagged. */
  singleSource: string[];
  /** Sources that disagree. The copywriter is told to omit these entirely. */
  conflicts: Array<{ field: string; values: Array<{ value: string; domain: string }> }>;
  notes: string[];
}

export interface GeneratedDescription {
  /** Short bullet-style summary for listing pages. */
  shortHtml: string;
  /** 150-160 char SEO meta description. */
  metaDescription: string;
  /** Full product description in the Design 911 house structure. */
  longHtml: string;
  /** Facts the writer used, traced back to where each came from. */
  factsUsed: Array<{ fact: string; source: string }>;
  /** Anything the writer deliberately left out, and why. */
  omitted: string[];
  model: string;
  generatedAt: string;
  /** Cost in USD for this single generation. */
  costUsd: number;
}

export type StageName = 'search' | 'fetch' | 'verify' | 'write';
export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export interface Stage {
  name: StageName;
  status: StageStatus;
  detail?: string;
  ms?: number;
}

/** Everything Forge knows about one part after a pipeline run. */
export interface EnrichedPart {
  part: Part;
  evidence: Evidence[];
  verification: Verification;
  description?: GeneratedDescription;
  stages: Stage[];
  error?: string;
}
