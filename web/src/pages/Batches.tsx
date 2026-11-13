import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CircleCheckBig,
  CloudUpload,
  FileStack,
  Gavel,
  Inbox,
  PackageOpen,
  Sparkles,
} from "lucide-react";
import { Link, useParams } from "react-router";
import { BarList, RingMeter, StackedBar, StatTile } from "../components/charts";
import { Hl, PageHeader } from "../components/Layout";
import { Card, EmptyState, ErrorState, LinkButton, LiveDot, Pill, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { ago, cn, humanize } from "../lib/format";
import { DOC_STAGES, DONE_STAGES, docType, PACK_STATUS, PRIORITIES } from "../lib/status";
import type { Batch, BatchStatus, PackStatus } from "../lib/types";

const BATCH_STATUS: Record<string, string> = {
  processing: "Reading documents",
  grouping: "Grouping into packs",
  grouped: "All documents read",
};

export function Batches() {
  const { batchId } = useParams();
  const batches = useQuery({ queryKey: ["batches"], queryFn: api.batches, refetchInterval: 10_000 });
  const selected = batchId ?? batches.data?.[0]?.id;

  return (
    <div>
      <PageHeader
        eyebrow="Live"
        icon={Activity}
        title={
          <>
            Live <Hl>batches</Hl>
          </>
        }
        description="Watch documents move from read to extracted and shipment packs appear. Refreshes every three seconds."
        actions={
          <LinkButton to="/upload" icon={CloudUpload} variant="ghost">
            New upload
          </LinkButton>
        }
      />

      {batches.isError ? (
        <ErrorState error={batches.error} onRetry={() => batches.refetch()} />
      ) : batches.isLoading ? (
        <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      ) : !batches.data?.length ? (
        <Card>
          <EmptyState
            icon={Inbox}
            title="No batches yet"
            action={
              <LinkButton to="/upload" icon={CloudUpload}>
                Upload documents
              </LinkButton>
            }
          >
            Upload a pile of supplier papers and this page comes alive.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
          <BatchList batches={batches.data} selected={selected} />
          {selected && <LiveBatch id={selected} />}
        </div>
      )}
    </div>
  );
}

function BatchList({ batches, selected }: { batches: Batch[]; selected?: string }) {
  return (
    <Card title="Recent batches" subtitle={`${batches.length} shown`} className="h-fit xl:sticky xl:top-6">
      <ul className="-mx-2 max-h-[70vh] space-y-1.5 overflow-y-auto px-2">
        {batches.map((b) => {
          const active = b.id === selected;
          const prio = PRIORITIES[b.priority];
          return (
            <li key={b.id}>
              <Link
                to={`/batches/${b.id}`}
                className={cn(
                  "block rounded-2xl p-3 ring-1 transition-all duration-200 ring-inset",
                  active ? "bg-surface-2 shadow-md ring-cyan-400/40" : "ring-transparent hover:bg-sunk",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-semibold text-ink">{b.name}</p>
                  {b.status !== "grouped" && <LiveDot color="#06b6d4" />}
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <Pill icon={prio.icon} className={cn(prio.pill, "px-2 py-0.5 text-[11px]")}>
                    {prio.label}
                  </Pill>
                  <span className="truncate text-xs text-ink-3">
                    {b.created_by} · {ago(b.created_at)}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function LiveBatch({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["batch", id], queryFn: () => api.batch(id), refetchInterval: 3_000 });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-[640px]" />;
  return <BatchView s={q.data} />;
}

function BatchView({ s }: { s: BatchStatus }) {
  const docs = s.documents;
  const total = Object.values(docs).reduce((a, b) => a + (b ?? 0), 0);
  const done = DONE_STAGES.reduce((a, k) => a + (docs[k] ?? 0), 0);
  const packCount = Object.values(s.packs).reduce((a, b) => a + (b ?? 0), 0);
  const attention = (s.packs.awaiting_approval ?? 0) + (s.packs.needs_review ?? 0);
  const queued = Object.values(s.queues).reduce((a, b) => a + b, 0);
  const live = s.status !== "grouped" || queued > 0 || !!s.packs.investigating || !!s.packs.open;
  const prio = PRIORITIES[s.priority];

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------ progress hero */}
      <section className="glass gradient-border relative overflow-hidden rounded-[28px] p-6" style={{ ["--gb" as string]: "linear-gradient(120deg, #22d3ee, #3b82f6 50%, #8b5cf6)" }}>
        <div className="pointer-events-none absolute -top-24 -right-16 size-72 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="relative flex flex-col gap-6 md:flex-row md:items-center">
          <RingMeter
            value={total ? done / total : 0}
            label={`${total ? Math.round((done / total) * 100) : 0}%`}
            sublabel={`${done} of ${total} read`}
            colors={["#22d3ee", "#6366f1"]}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {live ? (
                <Pill className="bg-cyan-400/15 text-cyan-700 ring-cyan-500/30 dark:text-cyan-300">
                  <span className="flex items-center gap-2">
                    <LiveDot color="#06b6d4" />
                    Live
                  </span>
                </Pill>
              ) : (
                <Pill icon={CircleCheckBig} className="bg-emerald-400/15 text-emerald-700 ring-emerald-500/30 dark:text-emerald-300">
                  Settled
                </Pill>
              )}
              <Pill icon={prio.icon} className={prio.pill}>
                {prio.label} priority
              </Pill>
            </div>
            <h2 className="mt-3 truncate text-2xl font-bold tracking-tight text-ink">{s.name}</h2>
            <p className="mt-1 text-sm text-ink-2">{BATCH_STATUS[s.status] ?? humanize(s.status)}</p>
            <div className="mt-5">
              <StackedBar segments={DOC_STAGES.map((st) => ({ key: st.key, label: st.label, value: docs[st.key] ?? 0, color: st.color }))} />
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ tiles */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-4">
        <StatTile label="Read and extracted" value={docs.extracted ?? 0} icon={FileStack} gradient="from-cyan-400 to-blue-500" />
        <StatTile label="Shipment packs" value={packCount} icon={PackageOpen} gradient="from-indigo-500 to-violet-500" />
        <StatTile label="Approved automatically" value={s.packs.auto_approved ?? 0} icon={Sparkles} gradient="from-emerald-400 to-teal-500" />
        <StatTile
          label="Need attention"
          value={attention}
          icon={Gavel}
          gradient="from-amber-400 to-rose-500"
          to="/review"
          hint={attention ? "Open the review queue →" : "Nothing waiting on a person"}
        />
      </div>

      {/* ------------------------------------------------ charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Documents by type" subtitle="Read and extracted so far" icon={FileStack}>
          <BarList
            color="#06b6d4"
            emptyText="No documents extracted yet."
            items={Object.entries(s.by_type)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => ({ key: k, label: docType(k).label, value: v, icon: docType(k).icon }))}
          />
        </Card>
        <Card title="Packs by status" subtitle="One pack per shipment" icon={PackageOpen}>
          <BarList
            emptyText="Packs appear once papers are grouped."
            items={(Object.entries(s.packs) as [PackStatus, number][])
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => ({ key: k, label: PACK_STATUS[k]?.label ?? k, value: v, color: PACK_STATUS[k]?.color }))}
          />
        </Card>
      </div>

      {Object.keys(s.live_counters).length > 0 && (
        <Card title="Live counters" subtitle="Ticked by the workers as each step finishes" icon={Activity}>
          <div className="flex flex-wrap gap-2">
            {Object.entries(s.live_counters).map(([k, v]) => (
              <span key={k} className="rounded-xl bg-sunk px-3 py-1.5 text-xs text-ink-2 ring-1 ring-line ring-inset">
                {humanize(k)} <b className="ml-1 text-ink tabular">{v}</b>
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
