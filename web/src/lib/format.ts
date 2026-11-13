import type { Money } from "./types";

export function toNumber(x: Money | unknown): number | null {
  if (x === null || x === undefined || x === "") return null;
  const n = typeof x === "number" ? x : Number(x);
  return Number.isFinite(n) ? n : null;
}

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const inrCompact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** ₹12,54,750.00 - Indian digit grouping, as the AP team reads amounts. */
export function rupees(x: Money): string {
  const n = toNumber(x);
  return n === null ? "—" : inr.format(n);
}

export function rupeesCompact(x: Money): string {
  const n = toNumber(x);
  return n === null ? "—" : inrCompact.format(n);
}

export function usd(x: Money, digits = 4): string {
  const n = toNumber(x);
  return n === null ? "—" : `$${n.toFixed(digits)}`;
}

export function pct(x: number | null | undefined, digits = 0): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(digits)}%`;
}

export function count(n: number): string {
  return new Intl.NumberFormat("en-IN").format(n);
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

const ACRONYMS: Record<string, string> = {
  ai: "AI",
  coa: "COA",
  erp: "ERP",
  eway: "E-way",
  grn: "GRN",
  gst: "GST",
  gstin: "GSTIN",
  hsn: "HSN",
  ifsc: "IFSC",
  json: "JSON",
  lr: "LR",
  pdf: "PDF",
  po: "PO",
  sku: "SKU",
};

/** SHORT_SHIPMENT -> Short shipment, LR_QTY_MISMATCH -> LR qty mismatch */
export function humanize(code: string): string {
  const words = code.replace(/[_-]+/g, " ").trim().toLowerCase().split(/\s+/);
  const out = words.map((w) => ACRONYMS[w] ?? w).join(" ");
  return out.charAt(0).toUpperCase() + out.slice(1);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] ?? "?").slice(0, 2)).toUpperCase();
}

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
