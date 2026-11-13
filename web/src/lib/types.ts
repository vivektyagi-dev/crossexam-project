// Shapes returned by app/api/main.py. Money arrives as a number or a decimal string.

export type Priority = "urgent" | "normal" | "bulk";
export type Role = "ap_executive" | "finance_manager";
export type Money = number | string | null | undefined;

export type DocStatus =
  | "queued"
  | "reading"
  | "read"
  | "classifying"
  | "split"
  | "ready"
  | "extracting"
  | "extracted"
  | "duplicate_file"
  | "failed";

export type PackStatus =
  | "open"
  | "waiting_for_invoice"
  | "auto_approved"
  | "investigating"
  | "awaiting_approval"
  | "needs_review"
  | "approved"
  | "rejected"
  | "exported"
  | "failed";

export interface Batch {
  id: string;
  name: string;
  priority: Priority;
  status: string;
  created_at: string;
  created_by: string;
}

export interface BatchStatus {
  id: string;
  name: string;
  status: string;
  priority: Priority;
  live_counters: Record<string, number>;
  documents: Partial<Record<DocStatus, number>>;
  by_type: Record<string, number>;
  packs: Partial<Record<PackStatus, number>>;
  queues: Record<string, number>;
}

export interface UploadResult {
  batch_id: string;
  accepted: number;
  duplicate_files: { filename: string; existing_document_id: string }[];
}

export interface PackSummary {
  id: string;
  batch_id: string;
  po_number: string | null;
  supplier_gstin: string | null;
  status: PackStatus;
  issue_codes: string[];
  invoice_total: Money;
  payable_amount: Money;
  finding: string | null;
  flags: string[] | null;
  updated_at: string;
}

export interface Issue {
  code: string;
  severity: "block" | "info" | string;
  message: string;
  evidence: Record<string, unknown>;
}

export interface MatchLine {
  sku: string;
  billed_qty?: string;
  received_qty?: string;
  pay_qty?: string;
  billed_price?: string;
  pay_price?: string;
  [key: string]: unknown;
}

export interface MatchResult {
  ok: boolean;
  route: string;
  issues: Issue[];
  invoice_total: string;
  payable_amount: string;
  debit_note_amount: string;
  lines: MatchLine[];
}

export interface PackDocument {
  id: string;
  filename: string;
  format: string;
  doc_type: string | null;
  pages: [number | null, number | null];
  flags: string[] | null;
  duplicate_of: string | null;
  confidence: number | null;
  model: string | null;
  escalated: boolean | null;
  validation_issues: string[] | null;
  data: Record<string, unknown> | null;
}

export interface PendingAction {
  id: number;
  tool: string;
  args: Record<string, unknown>;
  description: string;
  status: string;
  requires_role: Role | string | null;
  decided_by: string | null;
}

export interface AuditEntry {
  actor: string;
  role: string;
  action: string;
  detail: Record<string, unknown> | null;
  at: string;
}

export interface PackDetail extends PackSummary {
  match_result: MatchResult | null;
  proposal: Record<string, unknown> | null;
  documents: PackDocument[];
  actions: PendingAction[];
  audit: AuditEntry[];
  agent_cost_usd: string;
}

export interface Decision {
  action_id: number;
  type: "approve" | "edit" | "reject";
  args?: Record<string, unknown>;
  message?: string | null;
}

export interface OutboxEmail {
  id: number;
  pack_id: string;
  to: string;
  subject: string;
  body: string;
  status: string;
  created_at: string;
}

export interface Stats {
  window_hours: number;
  documents_extracted: number;
  documents_failed: number;
  low_confidence_rate: number;
  escalation_rate: number;
  packs: Partial<Record<PackStatus, number>>;
  routes: Record<string, number>;
  automation_rate: number;
  llm_cost_usd: string;
  cost_per_document_usd: string;
  cost_by_agent_usd: Record<string, string>;
}

export interface SheetPreview {
  sheets: { name: string; rows: string[][]; truncated: boolean }[];
}

export interface ExportResult {
  rows: number;
  csv: string;
  filename: string;
}
