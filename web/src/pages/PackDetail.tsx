import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Ban,
  CircleCheckBig,
  CircleDollarSign,
  Files,
  Gavel,
  History,
  Landmark,
  ListChecks,
  Quote,
  ReceiptText,
  Scale,
  ShieldAlert,
  Siren,
  TriangleAlert,
} from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { ActionCard, type Draft, jsonError, newDraft } from "../components/ActionCard";
import { StatTile } from "../components/charts";
import { Callout, FieldsPanel, OriginalPaper } from "../components/DocumentViewer";
import { Button, Card, ErrorState, inputClass, Pill, Skeleton, StatusPill } from "../components/ui";
import { api } from "../lib/api";
import { ago, cn, dateTime, humanize, rupees, toNumber, usd } from "../lib/format";
import { ROLE_LABELS, useIdentity } from "../lib/identity";
import { docType, issuePill, packTone } from "../lib/status";
import type { Decision, MatchLine, PackDetail, PendingAction } from "../lib/types";

const BUSY = ["investigating", "open"];

export function PackDetailPage() {
  const { packId = "" } = useParams();
  const [params] = useSearchParams();
  const q = useQuery({
    queryKey: ["pack", packId],
    queryFn: () => api.pack(packId),
    // slower when settled: a late invoice, an export or another reviewer can still change it
    refetchInterval: (query) => (BUSY.includes(query.state.data?.status ?? "") ? 4_000 : 15_000),
  });
  const back = `/review${params.toString() ? `?${params}` : ""}`;

  return (
    <div>
      <Link to={back} className="mb-6 inline-flex items-center gap-2 rounded-xl px-2 py-1 text-sm font-semibold text-ink-2 transition hover:bg-sunk hover:text-ink">
        <ArrowLeft className="size-4" />
        Review queue
      </Link>
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <div className="space-y-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-40" />
          <Skeleton className="h-[500px]" />
        </div>
      ) : (
        <PackView pack={q.data} />
      )}
    </div>
  );
}

function PackView({ pack }: { pack: PackDetail }) {
  const mr = pack.match_result;
  const blocking = mr?.issues.filter((i) => i.severity === "block") ?? [];
  const notes = mr?.issues.filter((i) => i.severity !== "block") ?? [];
  const tone = packTone(pack.status);

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------ header */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-start gap-4">
          <span className="mt-1 hidden size-14 shrink-0 place-items-center rounded-[20px] bg-linear-to-br from-amber-400 via-orange-500 to-rose-500 text-white shadow-xl shadow-orange-500/40 sm:grid">
            <tone.icon className="size-7" />
          </span>
          <div>
            <p className="text-xs font-bold tracking-[0.18em] text-orange-600 uppercase dark:text-amber-300">Shipment pack</p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight text-ink sm:text-4xl">{pack.po_number ?? "No PO"}</h1>
            <p className="mt-1.5 font-mono text-xs text-ink-3">
              {pack.supplier_gstin ?? "unknown supplier"} · updated {ago(pack.updated_at)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={pack.status} live={BUSY.includes(pack.status)} />
          <Link to={`/batches/${pack.batch_id}`} className="text-xs font-semibold text-ink-3 underline-offset-4 hover:text-ink hover:underline">
            View batch
          </Link>
        </div>
      </header>

      {pack.status === "investigating" && (
        <Callout tone="violet" icon={Siren}>
          The agent is working on this pack. This page refreshes on its own until it finishes.
        </Callout>
      )}

      {/* ------------------------------------------------ money */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Billed" display={rupees(pack.invoice_total)} icon={Landmark} gradient="from-violet-500 to-fuchsia-500" />
        <StatTile label="Match engine says pay" display={rupees(pack.payable_amount)} icon={Scale} gradient="from-emerald-400 to-teal-500" />
        <StatTile label="Debit note" display={rupees(mr?.debit_note_amount)} icon={ReceiptText} gradient="from-rose-500 to-pink-500" />
        <StatTile label="AI cost for this pack" display={usd(pack.agent_cost_usd)} icon={CircleDollarSign} gradient="from-sky-400 to-indigo-500" hint="From the cost ledger" />
      </div>
      <PaySplit billed={toNumber(pack.invoice_total)} pay={toNumber(pack.payable_amount)} debit={toNumber(mr?.debit_note_amount)} />

      {/* ------------------------------------------------ finding */}
      {pack.finding && <Finding text={pack.finding} />}

      {/* ------------------------------------------------ issues + lines */}
      {(blocking.length > 0 || notes.length > 0 || !!mr?.lines.length) && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="What does not add up" subtitle={blocking.length ? `${blocking.length} blocking issue${blocking.length > 1 ? "s" : ""}` : "Nothing blocks payment"} icon={TriangleAlert}>
            <ul className="space-y-3">
              {blocking.map((i) => (
                <li key={i.code + i.message} className="rounded-2xl bg-sunk p-4 ring-1 ring-line ring-inset">
                  <Pill className={issuePill(i.code)} icon={ShieldAlert}>
                    {humanize(i.code)}
                  </Pill>
                  <p className="mt-2 text-sm leading-relaxed text-ink">{i.message}</p>
                  {Object.keys(i.evidence ?? {}).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {Object.entries(i.evidence).map(([k, v]) => (
                        <span key={k} className="rounded-lg bg-surface-2 px-2 py-1 text-xs text-ink-2 ring-1 ring-line ring-inset">
                          {humanize(k)} <b className="text-ink tabular">{String(v)}</b>
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
              {notes.map((i) => (
                <li key={i.code + i.message} className="flex gap-2 px-1 text-[13px] text-ink-3">
                  <span className="font-semibold text-ink-2">{humanize(i.code)}:</span> {i.message}
                </li>
              ))}
              {!blocking.length && !notes.length && <p className="text-sm text-ink-3">Every check passed.</p>}
            </ul>
          </Card>
          {!!mr?.lines.length && (
            <Card title="Line by line" subtitle="Billed against received, as the match engine computed it" icon={ListChecks}>
              <LineTable lines={mr.lines} />
            </Card>
          )}
        </div>
      )}

      {/* ------------------------------------------------ papers */}
      <Papers pack={pack} />

      {/* ------------------------------------------------ decisions */}
      <Decisions pack={pack} />

      {/* ------------------------------------------------ audit */}
      {pack.audit.length > 0 && <Audit pack={pack} />}
    </div>
  );
}

function PaySplit({ billed, pay, debit }: { billed: number | null; pay: number | null; debit: number | null }) {
  if (!billed || pay === null) return null;
  const held = Math.max(0, debit ?? billed - pay);
  const payShare = Math.min(1, pay / billed);
  return (
    <div className="glass rounded-3xl px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
        <span className="font-semibold text-ink">Where the money goes</span>
        <span className="text-ink-3">
          {held > 0 ? `${((held / billed) * 100).toFixed(2)}% held back` : "Pay what was billed"}
        </span>
      </div>
      <div className="mt-3 flex h-3 gap-[2px] overflow-hidden rounded-[4px]">
        <motion.div className="h-full bg-linear-to-r from-emerald-500 to-teal-400" initial={{ flexGrow: 0 }} animate={{ flexGrow: payShare }} transition={{ duration: 1 }} />
        {held > 0 && <motion.div className="h-full min-w-1.5 bg-linear-to-r from-rose-500 to-pink-500" initial={{ flexGrow: 0 }} animate={{ flexGrow: 1 - payShare }} transition={{ duration: 1 }} />}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px] bg-emerald-500" /> Pay {rupees(pay)}
        </span>
        {held > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-[3px] bg-rose-500" /> Debit note {rupees(held)}
          </span>
        )}
      </div>
    </div>
  );
}

function Finding({ text }: { text: string }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass gradient-border relative overflow-hidden rounded-3xl p-6 sm:p-7"
      style={{ ["--gb" as string]: "linear-gradient(120deg, #8b5cf6, #d946ef 50%, #f59e0b)" }}
    >
      <Quote className="pointer-events-none absolute -right-2 -bottom-6 size-28 text-fuchsia-500/10" />
      <p className="text-xs font-bold tracking-[0.18em] text-fuchsia-600 uppercase dark:text-fuchsia-300">The agent’s finding</p>
      <p className="mt-3 font-serif text-xl leading-relaxed text-ink italic sm:text-2xl">“{text}”</p>
    </motion.section>
  );
}

function LineTable({ lines }: { lines: MatchLine[] }) {
  const n = (x: unknown) => toNumber(x as string);
  return (
    <div className="overflow-x-auto rounded-xl ring-1 ring-line ring-inset">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="bg-sunk text-right text-[11px] font-semibold tracking-wide whitespace-nowrap text-ink-3 uppercase">
            <th className="px-3 py-2 text-left">SKU</th>
            <th className="px-3 py-2">Billed</th>
            <th className="px-3 py-2">Received</th>
            <th className="px-3 py-2">Pay qty</th>
            <th className="px-3 py-2">Billed price</th>
            <th className="px-3 py-2">Pay price</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => {
            const short = (n(l.received_qty) ?? Infinity) < (n(l.billed_qty) ?? 0);
            const cheaper = (n(l.pay_price) ?? Infinity) < (n(l.billed_price) ?? 0);
            const bad = "font-semibold text-rose-600 dark:text-rose-300";
            return (
              <tr key={l.sku} className="border-t border-line text-right text-ink-2 tabular">
                <td className="px-3 py-2 text-left font-mono text-xs whitespace-nowrap text-ink">{l.sku}</td>
                <td className="px-3 py-2">{l.billed_qty ?? "—"}</td>
                <td className={cn("px-3 py-2", short && bad)}>{l.received_qty ?? "—"}</td>
                <td className={cn("px-3 py-2", short && bad)}>{l.pay_qty ?? "—"}</td>
                <td className="px-3 py-2">{rupees(l.billed_price)}</td>
                <td className={cn("px-3 py-2", cheaper && bad)}>{rupees(l.pay_price)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ papers
function Papers({ pack }: { pack: PackDetail }) {
  const [active, setActive] = useState(pack.documents[0]?.id);
  const doc = pack.documents.find((d) => d.id === active) ?? pack.documents[0];
  if (!doc) return null;
  return (
    <Card title="Papers in this shipment" subtitle="The original on the left, what was read on the right" icon={Files}>
      <div className="-mx-1 mb-5 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist">
        {pack.documents.map((d) => {
          const t = docType(d.doc_type);
          const on = d.id === doc.id;
          const injected = d.flags?.includes("possible_injection");
          return (
            <button
              key={d.id}
              role="tab"
              aria-selected={on}
              onClick={() => setActive(d.id)}
              className={cn(
                "flex shrink-0 items-center gap-2.5 rounded-2xl py-2 pr-4 pl-2 text-left ring-1 transition-all duration-200 ring-inset",
                on ? "bg-surface-2 shadow-md ring-line-strong" : "bg-sunk ring-line hover:ring-line-strong",
              )}
            >
              <span className={cn("grid size-8 place-items-center rounded-xl bg-linear-to-br text-white", on ? t.gradient : "from-slate-400 to-slate-500 opacity-70")}>
                <t.icon className="size-4" />
              </span>
              <span>
                <span className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
                  {t.label}
                  {injected && <ShieldAlert className="size-3.5 text-red-500" aria-label="Suspicious content" />}
                </span>
                <span className="block max-w-40 truncate text-[11px] text-ink-3">{d.duplicate_of ? "duplicate" : d.filename}</span>
              </span>
            </button>
          );
        })}
      </div>

      {doc.flags?.includes("possible_injection") && (
        <div className="mb-4">
          <Callout tone="red" icon={ShieldAlert}>
            This document contains text that tries to instruct the AI. It was removed before any AI saw it. Check the
            original carefully.
          </Callout>
        </div>
      )}
      {doc.duplicate_of && (
        <div className="mb-4">
          <Callout tone="amber" icon={TriangleAlert}>
            This looks like a duplicate of a document that was already processed.
          </Callout>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <div className="min-w-0">
          <p className="mb-2 truncate text-xs text-ink-3">
            Original · <span className="font-mono">{doc.filename}</span> · {humanize(doc.format)}
          </p>
          <OriginalPaper key={doc.id} doc={doc} />
        </div>
        <div className="min-w-0">
          <p className="mb-2 text-xs text-ink-3">What was read</p>
          <FieldsPanel doc={doc} />
        </div>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ decisions
function Decisions({ pack }: { pack: PackDetail }) {
  const pending = pack.actions.filter((a) => a.status === "pending");
  const decided = pack.actions.filter((a) => a.status !== "pending");

  return (
    <div className="space-y-4">
      {pack.status === "awaiting_approval" && pending.length > 0 ? (
        // keyed on the pending ids, so a new set of held actions starts with fresh drafts
        <PendingDecisions key={pending.map((a) => a.id).join(",")} pack={pack} pending={pending} />
      ) : ["needs_review", "waiting_for_invoice"].includes(pack.status) ? (
        <ManualDecision pack={pack} />
      ) : null}
      {decided.length > 0 && (
        <Card title="Decided actions" icon={Gavel}>
          <ul className="space-y-2">
            {decided.map((a) => (
              <DecidedRow key={a.id} action={a} />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

const OUTCOME: Record<string, string> = {
  approved: "bg-emerald-400/15 text-emerald-700 ring-emerald-500/30 dark:text-emerald-300",
  edited: "bg-amber-400/15 text-amber-700 ring-amber-500/30 dark:text-amber-300",
  rejected: "bg-rose-400/15 text-rose-700 ring-rose-500/30 dark:text-rose-300",
  superseded: "bg-slate-400/15 text-slate-700 ring-slate-500/30 dark:text-slate-300",
};

function DecidedRow({ action }: { action: PendingAction }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-sunk px-4 py-3 ring-1 ring-line ring-inset">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-ink">{humanize(action.tool)}</p>
        <p className="truncate text-xs text-ink-3">{action.description}</p>
      </div>
      <div className="flex items-center gap-2">
        {action.decided_by && <span className="text-xs text-ink-3">by {action.decided_by}</span>}
        <Pill className={OUTCOME[action.status] ?? undefined}>{humanize(action.status)}</Pill>
      </div>
    </li>
  );
}

function PendingDecisions({ pack, pending }: { pack: PackDetail; pending: PendingAction[] }) {
  const queryClient = useQueryClient();
  const { role } = useIdentity();
  const [drafts, setDrafts] = useState<Record<number, Draft>>(() => Object.fromEntries(pending.map((a) => [a.id, newDraft(a)])));

  const decided = pending.filter((a) => drafts[a.id]?.type).length;
  const invalid = pending.some((a) => drafts[a.id] && jsonError(drafts[a.id]));

  const submit = useMutation({
    mutationFn: (decisions: Decision[]) => api.decide(pack.id, decisions),
    onSuccess: () => {
      toast.success("Recorded. The agent is finishing up.");
      queryClient.invalidateQueries({ queryKey: ["pack", pack.id] });
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["batch", pack.batch_id] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e) => toast.error("Not recorded", { description: e instanceof Error ? e.message : String(e) }),
  });

  function onSubmit() {
    if (decided !== pending.length) {
      toast.error("Choose approve, edit or reject for every action first.");
      return;
    }
    const decisions: Decision[] = pending.map((a) => {
      const d = drafts[a.id];
      if (d.type === "edit") return { action_id: a.id, type: "edit", args: JSON.parse(d.json) };
      if (d.type === "reject") return { action_id: a.id, type: "reject", message: d.message || null };
      return { action_id: a.id, type: "approve" };
    });
    submit.mutate(decisions);
  }

  return (
    <section>
      <div className="mb-4 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-linear-to-br from-amber-400 to-rose-500 text-white shadow-lg shadow-rose-500/30">
          <Gavel className="size-5" />
        </span>
        <div>
          <h2 className="text-xl font-bold tracking-tight text-ink">The agent proposes. Nothing happens until you decide.</h2>
          <p className="mt-1 text-sm text-ink-2">
            The exception agent is paused at a saved checkpoint. When you submit, it resumes from exactly there.
          </p>
        </div>
      </div>
      <div className="space-y-4">
        {pending.map((a, i) => (
          <ActionCard
            key={a.id}
            index={i}
            action={a}
            role={role}
            draft={drafts[a.id] ?? newDraft(a)}
            onChange={(d) => setDrafts((prev) => ({ ...prev, [a.id]: d }))}
          />
        ))}
      </div>
      <div className="glass sticky bottom-4 z-20 mt-4 flex flex-col gap-3 rounded-2xl p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {pending.map((a) => (
              <span key={a.id} className={cn("h-1.5 w-6 rounded-full transition-colors", drafts[a.id]?.type ? "bg-linear-to-r from-amber-400 to-rose-500" : "bg-line-strong")} />
            ))}
          </div>
          <p className="text-sm text-ink-2">
            <b className="text-ink">{decided}</b> of {pending.length} decided · acting as {ROLE_LABELS[role]}
          </p>
        </div>
        <Button size="lg" icon={Gavel} gradient="from-amber-400 via-orange-500 to-rose-500" loading={submit.isPending} disabled={invalid} onClick={onSubmit}>
          Submit decisions
        </Button>
      </div>
    </section>
  );
}

function ManualDecision({ pack }: { pack: PackDetail }) {
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") => api.manualDecision(pack.id, decision, comment),
    onSuccess: (_, decision) => {
      toast.success(decision === "approve" ? "Approved" : "Rejected", { description: "Recorded in the audit trail." });
      queryClient.invalidateQueries({ queryKey: ["pack", pack.id] });
      queryClient.invalidateQueries({ queryKey: ["packs"] });
      queryClient.invalidateQueries({ queryKey: ["batch", pack.batch_id] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e) => toast.error("Not recorded", { description: e instanceof Error ? e.message : String(e) }),
  });
  return (
    <Card title="Your decision" subtitle="No agent proposal for this pack: approve or reject it directly." icon={Gavel}>
      <textarea
        className={cn(inputClass, "h-24 py-3")}
        placeholder="Comment for the audit trail"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Button variant="success" size="lg" icon={CircleCheckBig} loading={decide.isPending && decide.variables === "approve"} onClick={() => decide.mutate("approve")}>
          Approve
        </Button>
        <Button variant="danger" size="lg" icon={Ban} loading={decide.isPending && decide.variables === "reject"} onClick={() => decide.mutate("reject")}>
          Reject
        </Button>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ audit
function auditColor(action: string) {
  if (action.startsWith("approve") || action === "manual_approve") return "from-emerald-400 to-teal-500";
  if (action.startsWith("reject") || action === "manual_reject") return "from-rose-500 to-red-500";
  if (action.startsWith("edit")) return "from-amber-400 to-orange-500";
  if (action === "export") return "from-sky-400 to-cyan-400";
  return "from-violet-500 to-fuchsia-500";
}

function Audit({ pack }: { pack: PackDetail }) {
  return (
    <Card title="Audit trail" subtitle="Every human decision and export, in order" icon={History}>
      <ol className="relative space-y-5 pl-6 before:absolute before:top-2 before:bottom-2 before:left-[7px] before:w-px before:bg-line-strong">
        {pack.audit.map((a, i) => {
          const detail = Object.entries(a.detail ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
          return (
            <li key={i} className="relative">
              <span className={cn("absolute top-1 -left-6 size-[15px] rounded-full bg-linear-to-br ring-4 ring-page", auditColor(a.action))} />
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-sm font-semibold text-ink">{humanize(a.action.replace(":", " "))}</span>
                <span className="text-xs text-ink-3">
                  by {a.actor} ({ROLE_LABELS[a.role as keyof typeof ROLE_LABELS] ?? a.role}) · {dateTime(a.at)}
                </span>
              </div>
              {detail.length > 0 && (
                <p className="mt-1 text-[13px] break-words text-ink-2">
                  {detail.map(([k, v]) => `${humanize(k)}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ")}
                </p>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

