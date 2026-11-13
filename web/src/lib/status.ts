// One vocabulary for every status, document type and issue the screen shows. Each entry
// carries an icon and a label, so colour never carries meaning on its own.
import {
  Ban,
  BadgeCheck,
  CircleCheckBig,
  CircleDashed,
  CircleX,
  ClipboardList,
  Copy,
  FileQuestion,
  FileText,
  Hourglass,
  Layers,
  type LucideIcon,
  Package,
  Receipt,
  ReceiptText,
  Route,
  ScanSearch,
  Send,
  ShieldAlert,
  Sparkles,
  Truck,
  UserRoundCheck,
  Zap,
} from "lucide-react";
import type { DocStatus, PackStatus, Priority } from "./types";

export interface Tone {
  label: string;
  icon: LucideIcon;
  /** pill classes: tinted fill, readable text in both themes, hairline ring */
  pill: string;
  /** solid colour for bars and dots */
  color: string;
}

export const PACK_STATUS: Record<PackStatus, Tone> = {
  awaiting_approval: {
    label: "Waiting for your approval",
    icon: UserRoundCheck,
    pill: "bg-amber-400/15 text-amber-700 ring-amber-500/30 dark:text-amber-300",
    color: "#f59e0b",
  },
  needs_review: {
    label: "Needs a person",
    icon: ShieldAlert,
    pill: "bg-pink-400/15 text-pink-700 ring-pink-500/30 dark:text-pink-300",
    color: "#ec4899",
  },
  investigating: {
    label: "Agent investigating",
    icon: ScanSearch,
    pill: "bg-violet-400/15 text-violet-700 ring-violet-500/30 dark:text-violet-300",
    color: "#8b5cf6",
  },
  open: {
    label: "Being checked",
    icon: CircleDashed,
    pill: "bg-indigo-400/15 text-indigo-700 ring-indigo-500/30 dark:text-indigo-300",
    color: "#6366f1",
  },
  waiting_for_invoice: {
    label: "Waiting for invoice",
    icon: Hourglass,
    pill: "bg-slate-400/15 text-slate-700 ring-slate-500/30 dark:text-slate-300",
    color: "#94a3b8",
  },
  auto_approved: {
    label: "Approved automatically",
    icon: Sparkles,
    pill: "bg-emerald-400/15 text-emerald-700 ring-emerald-500/30 dark:text-emerald-300",
    color: "#10b981",
  },
  approved: {
    label: "Approved",
    icon: CircleCheckBig,
    pill: "bg-teal-400/15 text-teal-700 ring-teal-500/30 dark:text-teal-300",
    color: "#14b8a6",
  },
  exported: {
    label: "Exported to ERP",
    icon: Send,
    pill: "bg-sky-400/15 text-sky-700 ring-sky-500/30 dark:text-sky-300",
    color: "#0ea5e9",
  },
  rejected: {
    label: "Rejected",
    icon: Ban,
    pill: "bg-orange-400/15 text-orange-700 ring-orange-500/30 dark:text-orange-300",
    color: "#f97316",
  },
  failed: {
    label: "Failed",
    icon: CircleX,
    pill: "bg-red-400/15 text-red-700 ring-red-500/30 dark:text-red-300",
    color: "#ef4444",
  },
};

export const ATTENTION: PackStatus[] = ["awaiting_approval", "needs_review"];

export function packTone(status: string): Tone {
  return PACK_STATUS[status as PackStatus] ?? PACK_STATUS.open;
}

/** Document stages in pipeline order, for the stacked progress bar. */
export const DOC_STAGES: { key: DocStatus; label: string; color: string }[] = [
  { key: "queued", label: "Queued", color: "#64748b" },
  { key: "reading", label: "Reading", color: "#0ea5e9" },
  { key: "read", label: "Read", color: "#06b6d4" },
  { key: "classifying", label: "Classifying", color: "#6366f1" },
  { key: "ready", label: "Ready", color: "#8b5cf6" },
  { key: "extracting", label: "Extracting", color: "#d946ef" },
  { key: "extracted", label: "Extracted", color: "#10b981" },
  { key: "split", label: "Split bundle", color: "#14b8a6" },
  { key: "duplicate_file", label: "Duplicate file", color: "#f59e0b" },
  { key: "failed", label: "Failed", color: "#ef4444" },
];

export const DONE_STAGES: DocStatus[] = ["extracted", "split", "failed", "duplicate_file"];

export const DOC_TYPES: Record<string, { label: string; icon: LucideIcon; gradient: string }> = {
  invoice: { label: "Invoice", icon: Receipt, gradient: "from-violet-500 to-fuchsia-500" },
  packing_list: { label: "Packing list", icon: Package, gradient: "from-sky-500 to-cyan-400" },
  lorry_receipt: { label: "Lorry receipt", icon: Truck, gradient: "from-amber-500 to-orange-500" },
  eway_bill: { label: "E-way bill", icon: Route, gradient: "from-emerald-500 to-teal-400" },
  quality_certificate: { label: "Quality certificate", icon: BadgeCheck, gradient: "from-pink-500 to-rose-500" },
  credit_note: { label: "Credit note", icon: ReceiptText, gradient: "from-indigo-500 to-blue-500" },
  debit_note: { label: "Debit note", icon: ClipboardList, gradient: "from-rose-500 to-red-500" },
  other: { label: "Other", icon: FileQuestion, gradient: "from-slate-500 to-slate-400" },
};

export function docType(type: string | null | undefined) {
  return DOC_TYPES[type ?? ""] ?? { label: type ? type : "Unknown", icon: FileText, gradient: "from-slate-500 to-slate-400" };
}

export const PRIORITIES: Record<Priority, { label: string; hint: string; icon: LucideIcon; pill: string; active: string }> = {
  urgent: {
    label: "Urgent",
    hint: "Jumps ahead of the month-end backlog",
    icon: Zap,
    pill: "bg-rose-400/15 text-rose-700 ring-rose-500/30 dark:text-rose-300",
    active: "from-rose-500 to-orange-500",
  },
  normal: {
    label: "Normal",
    hint: "The everyday lane",
    icon: Layers,
    pill: "bg-violet-400/15 text-violet-700 ring-violet-500/30 dark:text-violet-300",
    active: "from-violet-500 to-fuchsia-500",
  },
  bulk: {
    label: "Bulk",
    hint: "Runs when there is spare capacity",
    icon: Copy,
    pill: "bg-cyan-400/15 text-cyan-700 ring-cyan-500/30 dark:text-cyan-300",
    active: "from-cyan-500 to-blue-500",
  },
};

/** Issue codes grouped so related problems share a colour family in chips. */
const ISSUE_FAMILY: Record<string, string> = {
  SHORT_SHIPMENT: "qty",
  LR_QTY_MISMATCH: "qty",
  PACKING_QTY_MISMATCH: "qty",
  OVER_ORDER_QTY: "qty",
  PRICE_MISMATCH: "money",
  TAX_RATE_MISMATCH: "money",
  EWAY_VALUE_MISMATCH: "money",
  POSSIBLE_DUPLICATE: "risk",
  SUSPICIOUS_CONTENT: "risk",
  LOW_CONFIDENCE: "risk",
  COA_FAILED: "quality",
  COA_BATCH_MISMATCH: "quality",
  MISSING_COA: "quality",
  SHORT_SHELF_LIFE: "quality",
};

const FAMILY_PILL: Record<string, string> = {
  qty: "bg-amber-400/12 text-amber-800 ring-amber-500/25 dark:text-amber-200",
  money: "bg-rose-400/12 text-rose-800 ring-rose-500/25 dark:text-rose-200",
  risk: "bg-red-500/12 text-red-800 ring-red-500/30 dark:text-red-200",
  quality: "bg-pink-400/12 text-pink-800 ring-pink-500/25 dark:text-pink-200",
  other: "bg-indigo-400/12 text-indigo-800 ring-indigo-500/25 dark:text-indigo-200",
};

export function issuePill(code: string): string {
  return FAMILY_PILL[ISSUE_FAMILY[code] ?? "other"];
}

