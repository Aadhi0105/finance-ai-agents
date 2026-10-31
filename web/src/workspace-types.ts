export type Artifact = { id: string; name: string; label: string; kind: string; sha256: string; bytes: number; url: string };
export type Run = {
  id: string; agent: string; workflow: string; title: string; entity: string; period: string;
  prepared_at: string; source_run_id: string; execution_status: string; review_status: 'review_required' | 'not_financial_approval';
  native_view?: { artifact_id: string; view_schema_version: number; adapter_id: string; adapter_version: string; source_artifact_ids: string[] } | null;
  summary: string; limitations: string[]; checks: string[];
  metrics: { label: string; value: string; basis: string }[]; artifacts: Artifact[]; report_id: string;
};
export type Workspace = { classification: string; prepared_at: string; code_commit: string | null; runs: Run[] };
