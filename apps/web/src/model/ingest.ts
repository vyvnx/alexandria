import type { IngestStage } from "./types";

/* Display copy + bar fill for each ingest stage. The backend pipeline emits
   these keys as it runs (see ingest/pipeline.py); the percents are milestones
   the ChartProgress bar snaps to, ascending in pipeline order. Labels are bare
   (no ellipsis) so they also read in a "Failed while <label>" toast. */
export const INGEST_STAGES: Record<IngestStage, { label: string; percent: number }> = {
  queued: { label: "Queued", percent: 6 },
  loading: { label: "Loading source", percent: 12 },
  visuals: { label: "Reading visuals", percent: 22 },
  summarizing: { label: "Summarizing", percent: 32 },
  extracting: { label: "Extracting entities", percent: 48 },
  embedding: { label: "Embedding", percent: 66 },
  resolving: { label: "Resolving duplicates", percent: 80 },
  relating: { label: "Mapping relationships", percent: 90 },
  linking: { label: "Linking similar", percent: 96 },
};
