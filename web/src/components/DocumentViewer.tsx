import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, FileQuestion, Loader2, ShieldAlert, Sparkles, TrendingUp } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { cn, humanize } from "../lib/format";
import { docType } from "../lib/status";
import type { PackDocument } from "../lib/types";
import { Pill } from "./ui";

type PaperKind = "pdf" | "image" | "json" | "sheet" | "other";

function paperKind(filename: string): PaperKind {
  const n = filename.toLowerCase();
  if (n.endsWith(".pdf")) return "pdf";
  if (/\.(png|jpe?g)$/.test(n)) return "image";
  if (n.endsWith(".json")) return "json";
  if (/\.(xlsx|xls|csv)$/.test(n)) return "sheet";
  return "other";
}

// ------------------------------------------------------------------ the original paper
export function OriginalPaper({ doc }: { doc: PackDocument }) {
  const kind = paperKind(doc.filename);
  const file = useQuery({
    queryKey: ["document-file", doc.id],
    queryFn: () => api.documentFile(doc.id),
    enabled: kind !== "sheet",
    staleTime: Infinity,
  });
  const sheet = useQuery({
    queryKey: ["document-table", doc.id],
    queryFn: () => api.documentTable(doc.id),
    enabled: kind === "sheet",
    staleTime: Infinity,
  });

  const failed = file.isError || sheet.isError;
  const loading = kind === "sheet" ? sheet.isLoading : file.isLoading;

  return (
    <div className="h-[640px] overflow-auto rounded-2xl bg-slate-200/70 p-3 ring-1 ring-line ring-inset dark:bg-black/30">
      {failed ? (
        <PaperMessage icon={FileQuestion}>Original file unavailable.</PaperMessage>
      ) : loading ? (
        <PaperMessage icon={Loader2} spin>
          Fetching the original…
        </PaperMessage>
      ) : kind === "pdf" && file.data ? (
        <PdfPages blob={file.data} pages={doc.pages} />
      ) : kind === "image" && file.data ? (
        <BlobImage blob={file.data} alt={doc.filename} />
      ) : kind === "json" && file.data ? (
        <JsonFromBlob blob={file.data} />
      ) : kind === "sheet" && sheet.data ? (
        <div className="space-y-4">
          {sheet.data.sheets.map((s) => (
            <div key={s.name} className="overflow-hidden rounded-xl bg-white shadow-xl">
              <p className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600">
                Sheet: {s.name}
                {s.truncated && " (first rows only)"}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-slate-800">
                  <tbody>
                    {s.rows.map((row, r) => (
                      <tr key={r} className="border-b border-slate-100 last:border-0">
                        {row.map((cell, c) => (
                          <td key={c} className="px-2.5 py-1.5 whitespace-nowrap">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      ) : (
        file.data && <DownloadBlob blob={file.data} filename={doc.filename} />
      )}
    </div>
  );
}

function PaperMessage({ icon: Icon, spin, children }: { icon: typeof Loader2; spin?: boolean; children: ReactNode }) {
  return (
    <div className="grid h-full place-items-center text-center text-sm text-ink-3">
      <div>
        <Icon className={cn("mx-auto mb-2 size-6", spin && "animate-spin")} />
        {children}
      </div>
    </div>
  );
}

function useObjectUrl(blob: Blob) {
  const url = useMemo(() => URL.createObjectURL(blob), [blob]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return url;
}

function BlobImage({ blob, alt }: { blob: Blob; alt: string }) {
  const url = useObjectUrl(blob);
  return <img src={url} alt={alt} className="mx-auto w-full rounded-lg bg-white shadow-xl" />;
}

function DownloadBlob({ blob, filename }: { blob: Blob; filename: string }) {
  const url = useObjectUrl(blob);
  return (
    <div className="grid h-full place-items-center">
      <a href={url} download={filename} className="glass flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-ink">
        <Download className="size-4" />
        Download original
      </a>
    </div>
  );
}

function JsonFromBlob({ blob }: { blob: Blob }) {
  const [value, setValue] = useState<unknown>(undefined);
  useEffect(() => {
    let alive = true;
    blob.text().then((t) => {
      if (!alive) return;
      try {
        setValue(JSON.parse(t));
      } catch {
        setValue(t);
      }
    });
    return () => {
      alive = false;
    };
  }, [blob]);
  if (value === undefined) return null;
  return <JsonView value={value} className="min-h-full bg-slate-950 text-slate-200" />;
}

/** Renders only the pages that belong to this document: a bundle's invoice shows the invoice's pages. */
function PdfPages({ blob, pages }: { blob: Blob; pages: PackDocument["pages"] }) {
  const host = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<{ status: "loading" | "ready" | "error"; range?: string }>({ status: "loading" });
  const fallback = useObjectUrl(blob);
  const [first, last] = pages;

  useEffect(() => {
    let cancelled = false;
    const node = host.current;
    if (!node) return;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        const pdf = await pdfjs.getDocument({ data: new Uint8Array(await blob.arrayBuffer()) }).promise;
        if (cancelled) return;
        const start = first ?? 1;
        const end = Math.min(first ? (last ?? first) : Math.min(pdf.numPages, 2), pdf.numPages);
        node.replaceChildren();
        const width = node.clientWidth || 600;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        for (let i = start; i <= end; i++) {
          const page = await pdf.getPage(i);
          if (cancelled) return;
          const scale = (width / page.getViewport({ scale: 1 }).width) * dpr;
          const viewport = page.getViewport({ scale });
          const canvas = document.createElement("canvas");
          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          canvas.className = "mb-3 w-full rounded-lg bg-white shadow-xl last:mb-0";
          node.appendChild(canvas);
          await page.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport }).promise;
        }
        if (!cancelled)
          setState({
            status: "ready",
            range: pdf.numPages > 1 ? `Page${end > start ? "s" : ""} ${start}${end > start ? `–${end}` : ""} of ${pdf.numPages}` : undefined,
          });
      } catch (e) {
        console.error("pdf render failed", e);
        if (!cancelled) setState({ status: "error" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [blob, first, last]);

  if (state.status === "error") return <iframe src={fallback} title="Original document" className="h-full w-full rounded-lg bg-white" />;
  return (
    <div>
      {state.status === "loading" && (
        <PaperMessage icon={Loader2} spin>
          Rendering pages…
        </PaperMessage>
      )}
      {state.range && <p className="mb-2 text-center text-[11px] font-semibold text-ink-3">{state.range}</p>}
      <div ref={host} />
    </div>
  );
}

// ------------------------------------------------------------------ what was read
const HIDDEN = new Set(["confidence", "uncertain_fields", "lines", "items"]);

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString("en-IN", { maximumFractionDigits: 4 });
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function FieldsPanel({ doc }: { doc: PackDocument }) {
  const data = doc.data ?? {};
  const confidence = typeof data.confidence === "number" ? data.confidence : doc.confidence;
  const uncertain = Array.isArray(data.uncertain_fields) ? (data.uncertain_fields as string[]) : [];
  const lines = (Array.isArray(data.lines) ? data.lines : Array.isArray(data.items) ? data.items : null) as
    | Record<string, unknown>[]
    | null;
  const fields = Object.entries(data).filter(([k]) => !HIDDEN.has(k));
  const t = docType(doc.doc_type);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Pill icon={t.icon} className="bg-sunk text-ink ring-line">
          {t.label}
        </Pill>
        {doc.model && (
          <Pill icon={Sparkles} className="bg-fuchsia-500/10 text-fuchsia-700 ring-fuchsia-500/25 dark:text-fuchsia-200" title="Model that read this document">
            {doc.model.startsWith("none:") ? `read by code (${doc.model.slice(5)})` : doc.model}
          </Pill>
        )}
        {doc.escalated && (
          <Pill icon={TrendingUp} className="bg-amber-500/12 text-amber-800 ring-amber-500/30 dark:text-amber-200">
            Escalated to stronger model
          </Pill>
        )}
      </div>

      {confidence !== null && confidence !== undefined && <ConfidenceMeter value={confidence} />}

      {uncertain.length > 0 && (
        <Callout tone="amber" icon={AlertTriangle}>
          <b>Unclear:</b> {uncertain.map(humanize).join(", ")}
        </Callout>
      )}
      {!!doc.validation_issues?.length && (
        <Callout tone="rose" icon={ShieldAlert}>
          <b>Checks failed:</b> {doc.validation_issues.map(humanize).join(", ")}
        </Callout>
      )}

      {fields.length > 0 ? (
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {fields.map(([k, v]) => (
            <div
              key={k}
              className={cn(
                "rounded-xl bg-sunk px-3 py-2 ring-1 ring-inset",
                uncertain.includes(k) ? "ring-amber-500/50" : "ring-line",
              )}
            >
              <dt className="text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{humanize(k)}</dt>
              <dd className="mt-0.5 text-sm font-medium break-words text-ink tabular">{display(v)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-ink-3">Nothing was extracted from this document.</p>
      )}

      {lines && lines.length > 0 && <LinesTable lines={lines} />}
    </div>
  );
}

function ConfidenceMeter({ value }: { value: number }) {
  // The confidence gate sends anything under 0.80 to a person.
  const tone = value >= 0.9 ? "#10b981" : value >= 0.8 ? "#f59e0b" : "#f43f5e";
  return (
    <div className="rounded-xl bg-sunk p-3 ring-1 ring-line ring-inset">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-ink-2">Confidence</span>
        <span className="font-semibold text-ink tabular">{Math.round(value * 100)}%</span>
      </div>
      <div className="relative mt-2 h-2 rounded-[4px]" style={{ background: `${tone}26` }}>
        <div className="h-full rounded-r-[4px]" style={{ width: `${value * 100}%`, background: tone }} />
        <span className="absolute -top-1 bottom-[-4px] w-px bg-ink-3" style={{ left: "80%" }} title="Confidence gate: 80%" />
      </div>
      <p className="mt-1.5 text-[11px] text-ink-3">Below the 80% gate, a person checks it.</p>
    </div>
  );
}

function LinesTable({ lines }: { lines: Record<string, unknown>[] }) {
  const cols = Array.from(new Set(lines.flatMap((l) => Object.keys(l))));
  return (
    <div className="overflow-x-auto rounded-xl ring-1 ring-line ring-inset">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="bg-sunk text-left text-[11px] font-semibold tracking-wide text-ink-3 uppercase">
            {cols.map((c) => (
              <th key={c} className="px-3 py-2 whitespace-nowrap">
                {humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} className="border-t border-line">
              {cols.map((c) => (
                <td key={c} className={cn("px-3 py-2 whitespace-nowrap text-ink-2 tabular", typeof l[c] === "number" && "text-right")}>
                  {display(l[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Callout({ tone, icon: Icon, children }: { tone: "amber" | "rose" | "violet" | "red"; icon: typeof AlertTriangle; children: ReactNode }) {
  const tones = {
    amber: "bg-amber-500/10 text-amber-900 ring-amber-500/30 dark:text-amber-100",
    rose: "bg-rose-500/10 text-rose-900 ring-rose-500/30 dark:text-rose-100",
    violet: "bg-violet-500/10 text-violet-900 ring-violet-500/30 dark:text-violet-100",
    red: "bg-red-500/12 text-red-900 ring-red-500/40 dark:text-red-100",
  };
  return (
    <div className={cn("flex items-start gap-2.5 rounded-xl px-3.5 py-3 text-[13px] leading-relaxed ring-1 ring-inset", tones[tone])}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

// ------------------------------------------------------------------ JSON
const TOKEN = /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const parts = useMemo(() => {
    const out: ReactNode[] = [];
    let last = 0;
    for (const m of text.matchAll(TOKEN)) {
      const i = m.index ?? 0;
      if (i > last) out.push(text.slice(last, i));
      const tok = m[0];
      const cls = tok.startsWith('"')
        ? tok.trimEnd().endsWith(":")
          ? "text-sky-300"
          : "text-emerald-300"
        : /true|false|null/.test(tok)
          ? "text-fuchsia-300"
          : "text-amber-300";
      out.push(
        <span key={i} className={cls}>
          {tok}
        </span>,
      );
      last = i + tok.length;
    }
    out.push(text.slice(last));
    return out;
  }, [text]);
  return (
    <pre className={cn("overflow-auto rounded-xl bg-slate-950/90 p-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-slate-300 ring-1 ring-white/10", className)}>
      {parts}
    </pre>
  );
}
