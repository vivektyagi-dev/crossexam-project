import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, CheckCheck, Gavel, HandCoins, Landmark, PackageOpen } from "lucide-react";
import { motion } from "motion/react";
import { Link, useSearchParams } from "react-router";
import { StatTile } from "../components/charts";
import { Hl, PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, Pill, Skeleton, StatusPill } from "../components/ui";
import { api } from "../lib/api";
import { ago, cn, humanize, rupees, rupeesCompact, toNumber } from "../lib/format";
import { ATTENTION, issuePill, PACK_STATUS } from "../lib/status";
import type { PackStatus, PackSummary } from "../lib/types";

const ORDER: PackStatus[] = [
  "awaiting_approval",
  "needs_review",
  "investigating",
  "open",
  "waiting_for_invoice",
  "auto_approved",
  "approved",
  "rejected",
  "exported",
  "failed",
];

export function useShownStatuses() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("show");
  const shown = raw === null ? ATTENTION : (raw.split(",").filter((s) => s in PACK_STATUS) as PackStatus[]);
  const toggle = (s: PackStatus) => {
    const next = shown.includes(s) ? shown.filter((x) => x !== s) : [...shown, s];
    setParams({ show: next.join(",") }, { replace: true });
  };
  return { shown, toggle, query: params.toString() };
}

export function ReviewQueue() {
  const { shown, toggle, query } = useShownStatuses();
  const packs = useQuery({
    queryKey: ["packs", shown],
    queryFn: () => api.packs(shown),
    enabled: shown.length > 0,
    refetchInterval: 10_000,
  });
  const rows = shown.length ? (packs.data ?? []) : [];
  const billed = rows.reduce((s, p) => s + (toNumber(p.invoice_total) ?? 0), 0);
  const payable = rows.reduce((s, p) => s + (toNumber(p.payable_amount) ?? 0), 0);

  return (
    <div>
      <PageHeader
        eyebrow="Human in the loop"
        icon={Gavel}
        title={
          <>
            Review <Hl>queue</Hl>
          </>
        }
        description="The packs the agents could not settle on their own, with the evidence, the agent's finding and the actions waiting for your decision."
      />

      <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {ORDER.map((s) => {
          const tone = PACK_STATUS[s];
          const on = shown.includes(s);
          return (
            <button
              key={s}
              onClick={() => toggle(s)}
              aria-pressed={on}
              className={cn(
                "flex items-center gap-2 rounded-full px-3.5 py-2 text-[13px] font-semibold ring-1 transition-all duration-200 ring-inset",
                on ? "bg-surface-2 text-ink shadow-md ring-line-strong" : "text-ink-3 ring-line hover:text-ink-2",
              )}
            >
              <span
                className={cn("size-2.5 rounded-full transition-all", on ? "scale-110" : "opacity-40")}
                style={{ background: tone.color, boxShadow: on ? `0 0 12px ${tone.color}` : undefined }}
              />
              {tone.label}
            </button>
          );
        })}
      </div>

      {shown.length > 0 && rows.length > 0 && (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatTile label="Packs in view" value={rows.length} icon={PackageOpen} gradient="from-amber-400 to-orange-500" />
          <StatTile label="Billed" display={rupeesCompact(billed)} hint={rupees(billed)} icon={Landmark} gradient="from-violet-500 to-fuchsia-500" />
          <StatTile
            label="Held back by the match engine"
            display={rupeesCompact(Math.max(0, billed - payable))}
            hint="Billed minus what the papers support"
            icon={HandCoins}
            gradient="from-rose-500 to-pink-500"
          />
        </div>
      )}

      {!shown.length ? (
        <Card>
          <EmptyState icon={Gavel} title="Pick at least one status">
            Choose which packs to show with the filters above.
          </EmptyState>
        </Card>
      ) : packs.isError ? (
        <ErrorState error={packs.error} onRetry={() => packs.refetch()} />
      ) : packs.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : !rows.length ? (
        <Card>
          <EmptyState icon={CheckCheck} title="Nothing waiting">
            Every pack in this view has been handled.
          </EmptyState>
        </Card>
      ) : (
        <div className="glass overflow-hidden rounded-3xl">
          <div className="hidden grid-cols-[1.4fr_1.2fr_1.6fr_1fr_1fr_auto] gap-4 border-b border-line px-6 py-3 text-[11px] font-bold tracking-[0.12em] text-ink-3 uppercase lg:grid">
            <span>Shipment</span>
            <span>Status</span>
            <span>What does not add up</span>
            <span className="text-right">Billed</span>
            <span className="text-right">Pay</span>
            <span className="w-5" />
          </div>
          <ul>
            {rows.map((p, i) => (
              <PackRow key={p.id} pack={p} index={i} query={query} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PackRow({ pack, index, query }: { pack: PackSummary; index: number; query: string }) {
  const billed = toNumber(pack.invoice_total);
  const pay = toNumber(pack.payable_amount);
  const held = billed !== null && pay !== null ? billed - pay : 0;
  return (
    <motion.li
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: Math.min(index, 12) * 0.03 }}
      className="border-b border-line last:border-b-0"
    >
      <Link
        to={`/review/${pack.id}${query ? `?${query}` : ""}`}
        className="group grid grid-cols-1 gap-3 px-5 py-4 transition-colors hover:bg-sunk sm:px-6 lg:grid-cols-[1.4fr_1.2fr_1.6fr_1fr_1fr_auto] lg:items-center lg:gap-4"
      >
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{pack.po_number ?? "No PO"}</p>
          <p className="truncate font-mono text-xs text-ink-3">
            {pack.supplier_gstin ?? "unknown supplier"} · {ago(pack.updated_at)}
          </p>
        </div>
        <div>
          <StatusPill status={pack.status} live={pack.status === "investigating"} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {pack.issue_codes.length ? (
            pack.issue_codes.map((c) => (
              <Pill key={c} className={cn(issuePill(c), "px-2 py-0.5 text-[11px]")}>
                {humanize(c)}
              </Pill>
            ))
          ) : (
            <span className="text-xs text-ink-3">No issues</span>
          )}
        </div>
        <div className="flex justify-between text-sm lg:block lg:text-right">
          <span className="text-ink-3 lg:hidden">Billed</span>
          <span className="font-semibold text-ink tabular">{rupees(pack.invoice_total)}</span>
        </div>
        <div className="flex justify-between text-sm lg:block lg:text-right">
          <span className="text-ink-3 lg:hidden">Pay</span>
          <span>
            <span className="block font-semibold text-ink tabular">{rupees(pack.payable_amount)}</span>
            {held > 0.5 && <span className="block text-xs font-medium text-rose-600 tabular dark:text-rose-300">−{rupees(held)}</span>}
          </span>
        </div>
        <ArrowUpRight className="hidden size-5 text-ink-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-ink lg:block" />
      </Link>
    </motion.li>
  );
}
