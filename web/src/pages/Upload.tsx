import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CircleCheckBig,
  CloudUpload,
  Copy,
  FileImage,
  FileJson,
  FileSpreadsheet,
  FileText,
  type LucideIcon,
  Rocket,
  Scissors,
  ScanSearch,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Hl, PageHeader } from "../components/Layout";
import { Button, Card, Field, IconBadge, inputClass, LinkButton } from "../components/ui";
import { api } from "../lib/api";
import { bytes, cn } from "../lib/format";
import { PRIORITIES } from "../lib/status";
import type { Priority, UploadResult } from "../lib/types";

type Kind = "pdf" | "image" | "sheet" | "json";

const KINDS: Record<Kind, { label: string; hint: string; icon: LucideIcon; gradient: string; ext: string[] }> = {
  pdf: { label: "PDF", hint: "Digital or scanned", icon: FileText, gradient: "from-rose-500 to-pink-500", ext: [".pdf"] },
  image: { label: "Photos", hint: "PNG and JPG scans", icon: FileImage, gradient: "from-amber-400 to-orange-500", ext: [".png", ".jpg", ".jpeg"] },
  sheet: { label: "Spreadsheets", hint: "Excel and CSV", icon: FileSpreadsheet, gradient: "from-emerald-400 to-teal-500", ext: [".xlsx", ".xls", ".csv"] },
  json: { label: "GST JSON", hint: "E-way bills", icon: FileJson, gradient: "from-sky-400 to-indigo-500", ext: [".json"] },
};

const ACCEPT = Object.values(KINDS).flatMap((k) => k.ext);

function kindOf(name: string): Kind | null {
  const lower = name.toLowerCase();
  return (Object.keys(KINDS) as Kind[]).find((k) => KINDS[k].ext.some((e) => lower.endsWith(e))) ?? null;
}

const fileKey = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;

export function Upload() {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [priority, setPriority] = useState<Priority>("normal");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  const totals = useMemo(() => {
    const byKind = { pdf: 0, image: 0, sheet: 0, json: 0 } as Record<Kind, number>;
    files.forEach((f) => byKind[kindOf(f.name)!]++);
    return { byKind, size: files.reduce((s, f) => s + f.size, 0) };
  }, [files]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list);
    const ok = incoming.filter((f) => kindOf(f.name));
    const skipped = incoming.length - ok.length;
    if (skipped) toast.warning(`${skipped} file${skipped > 1 ? "s" : ""} skipped`, { description: "Only PDF, images, Excel, CSV and JSON can be read." });
    setFiles((prev) => {
      const seen = new Set(prev.map(fileKey));
      return [...prev, ...ok.filter((f) => !seen.has(fileKey(f)))];
    });
    setResult(null);
  }

  async function submit() {
    if (!files.length) {
      toast.error("Choose at least one file first.");
      return;
    }
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    form.append("name", name);
    form.append("priority", priority);
    setProgress(0);
    try {
      const body = await api.uploadBatch(form, setProgress);
      setResult(body);
      setFiles([]);
      setName("");
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      toast.success(`Accepted ${body.accepted} new file${body.accepted === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error("Upload failed", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setProgress(null);
    }
  }

  const uploading = progress !== null;

  return (
    <div>
      <PageHeader
        eyebrow="Intake"
        icon={CloudUpload}
        title={
          <>
            Upload <Hl>documents</Hl>
          </>
        }
        description="Drop invoices, packing lists, lorry receipts, e-way bills, quality certificates and credit notes in any format. Mixed bundles are split automatically."
      />

      {/* ------------------------------------------------ settings, above the drop zone */}
      <Card title="Batch settings" icon={Rocket} className="mb-6">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,2.2fr)]">
          <Field label="Batch name" hint="Optional. Defaults to “Upload by” and your name.">
            <input className={inputClass} placeholder="Month-end, week 4" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div>
            <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">Priority</span>
            <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Priority">
              {(Object.keys(PRIORITIES) as Priority[]).map((p) => {
                const meta = PRIORITIES[p];
                const active = p === priority;
                return (
                  <button
                    key={p}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setPriority(p)}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl p-3 text-left ring-1 transition-all duration-200 ring-inset",
                      active ? "bg-surface-2 shadow-md ring-line-strong" : "bg-sunk ring-line hover:ring-line-strong",
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-9 shrink-0 place-items-center rounded-xl transition-all",
                        active ? cn("bg-linear-to-br text-white shadow-md", meta.active) : "bg-sunk text-ink-3",
                      )}
                    >
                      <meta.icon className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-ink">{meta.label}</span>
                      <span className="block text-xs text-ink-3">{meta.hint}</span>
                    </span>
                    <span
                      className={cn(
                        "size-4 shrink-0 rounded-full ring-2 transition-all ring-inset",
                        active ? "bg-linear-to-br ring-transparent " + meta.active : "ring-line-strong",
                      )}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-2">
            {files.length ? (
              <>
                <b className="text-ink">
                  {files.length} file{files.length === 1 ? "" : "s"}
                </b>{" "}
                ready · {bytes(totals.size)} · {PRIORITIES[priority].label.toLowerCase()} priority
              </>
            ) : (
              "Add files below, then start processing."
            )}
          </p>
          <div className="sm:w-64">
            <Button size="lg" className="w-full" icon={Rocket} onClick={submit} loading={uploading} disabled={!files.length}>
              {uploading ? `Uploading ${Math.round((progress ?? 0) * 100)}%` : "Start processing"}
            </Button>
            {uploading && (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-sunk">
                <motion.div
                  className="h-full rounded-full bg-linear-to-r from-fuchsia-500 via-violet-500 to-cyan-400"
                  animate={{ width: `${(progress ?? 0) * 100}%` }}
                />
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          {/* ------------------------------------------------ drop zone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles(e.dataTransfer.files);
            }}
            className={cn(
              "relative overflow-hidden rounded-[32px] p-[2px] transition-transform duration-300",
              dragging && "scale-[1.01]",
            )}
          >
            <div
              className={cn(
                "spin-slow absolute -inset-[60%] transition-opacity duration-500",
                dragging ? "opacity-100" : "opacity-40",
              )}
              style={{ background: "conic-gradient(from 0deg, #d946ef, #8b5cf6, #06b6d4, #f59e0b, #d946ef)" }}
            />
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="glass relative flex w-full flex-col items-center rounded-[30px] border-none! bg-page/80! px-6 py-14 text-center sm:py-16"
            >
              <motion.span animate={{ y: dragging ? -8 : [0, -6, 0] }} transition={dragging ? { duration: 0.2 } : { duration: 3, repeat: Infinity, ease: "easeInOut" }}>
                <IconBadge icon={CloudUpload} size="lg" className="size-20! rounded-[26px]!" />
              </motion.span>
              <p className="mt-6 text-xl font-semibold tracking-tight text-ink">
                {dragging ? "Let go to add the files" : "Drag papers here, or click to browse"}
              </p>
              <p className="mt-1.5 text-sm text-ink-3">PDF, scans, phone photos, Excel, CSV or GST JSON · any number of files</p>
              <div className="mt-7 flex flex-wrap justify-center gap-2.5">
                {(Object.keys(KINDS) as Kind[]).map((k) => {
                  const kind = KINDS[k];
                  return (
                    <span key={k} className="flex items-center gap-2 rounded-2xl bg-sunk py-1.5 pr-3.5 pl-1.5 ring-1 ring-line ring-inset">
                      <span className={cn("grid size-7 place-items-center rounded-xl bg-linear-to-br text-white", kind.gradient)}>
                        <kind.icon className="size-3.5" />
                      </span>
                      <span className="text-left">
                        <span className="block text-xs font-semibold text-ink">{kind.label}</span>
                        <span className="block text-[11px] text-ink-3">{kind.hint}</span>
                      </span>
                    </span>
                  );
                })}
              </div>
            </button>
            <input
              ref={input}
              type="file"
              multiple
              accept={ACCEPT.join(",")}
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {/* ------------------------------------------------ selected files */}
          <AnimatePresence>
            {files.length > 0 && (
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 12 }}>
                <Card
                  title={`${files.length} file${files.length === 1 ? "" : "s"} ready · ${bytes(totals.size)}`}
                  subtitle={(Object.keys(KINDS) as Kind[])
                    .filter((k) => totals.byKind[k])
                    .map((k) => `${totals.byKind[k]} ${KINDS[k].label.toLowerCase()}`)
                    .join(" · ")}
                  action={
                    <Button variant="subtle" size="sm" icon={Trash2} onClick={() => setFiles([])} disabled={uploading}>
                      Clear
                    </Button>
                  }
                >
                  <ul className="-mx-2 max-h-[360px] space-y-1 overflow-y-auto px-2">
                    {files.map((f) => {
                      const kind = KINDS[kindOf(f.name)!];
                      return (
                        <li key={fileKey(f)} className="group flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-sunk">
                          <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg bg-linear-to-br text-white", kind.gradient)}>
                            <kind.icon className="size-4" />
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm text-ink">{f.name}</span>
                          <span className="text-xs text-ink-3 tabular">{bytes(f.size)}</span>
                          <button
                            onClick={() => setFiles((prev) => prev.filter((x) => x !== f))}
                            disabled={uploading}
                            className="grid size-7 place-items-center rounded-lg text-ink-3 opacity-0 transition group-hover:opacity-100 hover:bg-rose-500/15 hover:text-rose-500"
                            aria-label={`Remove ${f.name}`}
                          >
                            <X className="size-4" />
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ------------------------------------------------ result */}
          <AnimatePresence>{result && <ResultPanel result={result} onDismiss={() => setResult(null)} />}</AnimatePresence>
        </div>

        {/* ------------------------------------------------ tips, beside the drop zone */}
        <Card title="Good to know" icon={ScanSearch} className="h-fit">
          <ul className="space-y-4">
            <Tip icon={Scissors} gradient="from-violet-500 to-fuchsia-500" title="Bundles are split">
              One scan holding an invoice, packing list and lorry receipt becomes three documents.
            </Tip>
            <Tip icon={Copy} gradient="from-amber-400 to-orange-500" title="Never read twice">
              The same file uploaded again is skipped. A scanned copy of an invoice is caught as a possible duplicate
              after reading.
            </Tip>
            <Tip icon={Terminal} gradient="from-sky-400 to-indigo-500" title="Demo data">
              Run <code className="font-mono text-[12px]">scripts\demo-data.cmd 60</code>, then upload everything in{" "}
              <code className="font-mono text-[12px]">data\generated\files</code>.
            </Tip>
          </ul>
        </Card>
      </div>
    </div>
  );
}

function Tip({ icon: Icon, gradient, title, children }: { icon: LucideIcon; gradient: string; title: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className={cn("grid size-8 shrink-0 place-items-center rounded-xl bg-linear-to-br text-white", gradient)}>
        <Icon className="size-4" />
      </span>
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-3">{children}</p>
      </div>
    </li>
  );
}

function ResultPanel({ result, onDismiss }: { result: UploadResult; onDismiss: () => void }) {
  const dupes = result.duplicate_files.length;
  const nothingNew = result.accepted === 0;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97, y: 16 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      className="glass gradient-border relative overflow-hidden rounded-[28px] p-6"
      style={{ ["--gb" as string]: "linear-gradient(120deg, #10b981, #06b6d4, #8b5cf6)" }}
    >
      <div className="pointer-events-none absolute -top-20 -left-10 size-60 rounded-full bg-emerald-500/20 blur-3xl" />
      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center">
        <motion.span initial={{ scale: 0, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", delay: 0.1 }}>
          <IconBadge icon={nothingNew ? Copy : CircleCheckBig} size="lg" gradient={nothingNew ? "from-amber-400 to-orange-500" : "from-emerald-400 to-teal-500"} />
        </motion.span>
        <div className="flex-1">
          <p className="text-xl font-semibold tracking-tight text-ink">
            {nothingNew ? "Nothing new in this upload" : `Accepted ${result.accepted} new file${result.accepted === 1 ? "" : "s"}`}
          </p>
          <p className="mt-1 text-sm text-ink-2">
            {dupes
              ? `${dupes} file${dupes === 1 ? " was" : "s were"} already uploaded before and ${dupes === 1 ? "was" : "were"} skipped.`
              : "The readers have picked them up. Watch the documents being read and the packs appear."}
          </p>
        </div>
        <div className="flex gap-2">
          {!nothingNew && (
            <LinkButton to={`/batches/${result.batch_id}`} icon={ArrowRight} gradient="from-cyan-400 via-sky-500 to-indigo-500">
              Watch it live
            </LinkButton>
          )}
          <Button variant="subtle" icon={X} onClick={onDismiss} aria-label="Dismiss" />
        </div>
      </div>
      {dupes > 0 && (
        <details className="relative mt-4 rounded-2xl bg-sunk p-3 text-sm ring-1 ring-line ring-inset">
          <summary className="cursor-pointer font-semibold text-ink-2">Skipped files</summary>
          <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto font-mono text-xs text-ink-3">
            {result.duplicate_files.map((d) => (
              <li key={d.filename + d.existing_document_id}>{d.filename}</li>
            ))}
          </ul>
        </details>
      )}
    </motion.div>
  );
}
