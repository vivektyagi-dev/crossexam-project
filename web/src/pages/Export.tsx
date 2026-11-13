import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BotOff, CircleCheckBig, Download, FileOutput, Inbox, Lock, Mail, MailCheck, Repeat2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo } from "react";
import { toast } from "sonner";
import { Hl, PageHeader } from "../components/Layout";
import { Button, Card, EmptyState, ErrorState, IconBadge, Pill, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { ago, humanize, rupees } from "../lib/format";
import type { ExportResult, OutboxEmail } from "../lib/types";

const GUARANTEES = [
  { icon: CircleCheckBig, title: "Approved invoices only", text: "Approved by a person or by the match engine.", gradient: "from-emerald-400 to-teal-500" },
  { icon: Repeat2, title: "Each invoice exactly once", text: "Running it twice is harmless: the second export is empty.", gradient: "from-teal-400 to-cyan-500" },
  { icon: BotOff, title: "No agent can trigger it", text: "Export is plain code. It is not a tool any agent holds.", gradient: "from-cyan-400 to-sky-500" },
];

export function ExportPage() {
  const queryClient = useQueryClient();
  const run = useMutation({
    mutationFn: api.createExport,
    onSuccess: (r) => {
      if (!r.rows) return toast.info("Nothing new to export");
      toast.success(`${r.rows} invoice${r.rows === 1 ? "" : "s"} exported`);
      // exported packs change status: refresh every view that shows them
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["pack"] });
      queryClient.invalidateQueries({ queryKey: ["batch"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e) => toast.error("Export failed", { description: e instanceof Error ? e.message : String(e) }),
  });

  return (
    <div>
      <PageHeader
        eyebrow="Ledger"
        icon={FileOutput}
        title={
          <>
            Export to <Hl>ERP</Hl>
          </>
        }
        description="Exports every approved invoice that has not been exported yet, as a CSV your ERP can import."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <section
            className="glass gradient-border relative overflow-hidden rounded-[28px] p-6 sm:p-8"
            style={{ ["--gb" as string]: "linear-gradient(120deg, #34d399, #2dd4bf 50%, #22d3ee)" }}
          >
            <div className="pointer-events-none absolute -top-24 -right-20 size-72 rounded-full bg-emerald-500/20 blur-3xl" />
            <div className="relative flex items-start gap-4">
              <IconBadge icon={Lock} size="lg" />
              <div>
                <h2 className="text-xl font-bold tracking-tight text-ink">Money leaves only through code</h2>
                <p className="mt-1 max-w-lg text-sm leading-relaxed text-ink-2">
                  The agents read and investigate. The export that releases payments is ordinary code with an idempotency
                  key per invoice.
                </p>
              </div>
            </div>
            <div className="relative mt-6 grid gap-3 sm:grid-cols-3">
              {GUARANTEES.map((g) => (
                <div key={g.title} className="rounded-2xl bg-sunk p-4 ring-1 ring-line ring-inset">
                  <IconBadge icon={g.icon} size="sm" gradient={g.gradient} />
                  <p className="mt-3 text-sm font-semibold text-ink">{g.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-ink-3">{g.text}</p>
                </div>
              ))}
            </div>
            <div className="relative mt-6">
              <Button size="lg" icon={FileOutput} onClick={() => run.mutate()} loading={run.isPending}>
                Create export
              </Button>
            </div>
          </section>

          <AnimatePresence mode="wait">{run.data && <ExportOutcome key={run.submittedAt} result={run.data} />}</AnimatePresence>
        </div>

        <Outbox />
      </div>
    </div>
  );
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell || row.length) rows.push([...row, cell]);
  return rows.filter((r) => r.some((c) => c !== ""));
}

const MONEY_COLUMNS = new Set(["invoice_total", "pay_amount", "debit_note"]);

function ExportOutcome({ result }: { result: ExportResult }) {
  const [header, ...rows] = useMemo(() => parseCsv(result.csv), [result.csv]);

  function download() {
    const url = URL.createObjectURL(new Blob([result.csv], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: result.filename });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  if (!result.rows)
    return (
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
        <Card>
          <EmptyState icon={Repeat2} title="Nothing new to export">
            Every approved invoice has already been exported. Each invoice can only ever be exported once, so running this
            again is harmless.
          </EmptyState>
        </Card>
      </motion.div>
    );

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <Card
        title={`${result.rows} invoice${result.rows === 1 ? "" : "s"} exported`}
        subtitle={result.filename}
        icon={CircleCheckBig}
        action={
          <Button icon={Download} size="sm" onClick={download}>
            Download CSV
          </Button>
        }
      >
        <div className="overflow-x-auto rounded-xl ring-1 ring-line ring-inset">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-sunk text-left text-[11px] font-semibold tracking-wide whitespace-nowrap text-ink-3 uppercase">
                {header?.map((h) => (
                  <th key={h} className={`px-3 py-2 ${MONEY_COLUMNS.has(h) ? "text-right" : ""}`}>
                    {humanize(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((r, i) => (
                <tr key={i} className="border-t border-line whitespace-nowrap text-ink-2">
                  {r.map((c, j) => (
                    <td key={j} className={`px-3 py-2 ${MONEY_COLUMNS.has(header?.[j] ?? "") ? "text-right text-ink tabular" : ""} ${header?.[j] === "pack_id" || header?.[j] === "supplier_gstin" ? "font-mono text-xs" : ""}`}>
                      {MONEY_COLUMNS.has(header?.[j] ?? "") ? rupees(c) : c}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 50 && <p className="mt-2 text-xs text-ink-3">Showing the first 50 of {rows.length} rows. The CSV has them all.</p>}
      </Card>
    </motion.div>
  );
}

function Outbox() {
  const q = useQuery({ queryKey: ["outbox"], queryFn: api.outbox, refetchInterval: 15_000 });
  return (
    <Card title="Supplier emails" subtitle="Queued after a person approved the agent's draft" icon={MailCheck} className="h-fit">
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : q.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : !q.data?.length ? (
        <EmptyState icon={Inbox} title="None yet">
          Approve a pack with a drafted supplier email and it lands here.
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {q.data.map((m) => (
            <Email key={m.id} mail={m} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function Email({ mail }: { mail: OutboxEmail }) {
  return (
    <li>
      <details className="group rounded-2xl bg-sunk ring-1 ring-line ring-inset open:bg-surface-2">
        <summary className="flex cursor-pointer list-none items-start gap-3 p-3.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-linear-to-br from-emerald-400 to-cyan-500 text-white">
            <Mail className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink">{mail.subject}</span>
            <span className="block truncate text-xs text-ink-3">
              {mail.to} · {ago(mail.created_at)}
            </span>
          </span>
          <Pill className="bg-emerald-400/15 px-2 py-0.5 text-[11px] text-emerald-700 ring-emerald-500/30 dark:text-emerald-300">{humanize(mail.status)}</Pill>
        </summary>
        <p className="border-t border-line px-4 py-3 text-[13px] leading-relaxed break-words whitespace-pre-wrap text-ink-2">{mail.body}</p>
      </details>
    </li>
  );
}
