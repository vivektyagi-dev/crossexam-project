import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Bot,
  CircleDollarSign,
  FileStack,
  FileX2,
  Flower2,
  Gauge,
  type LucideIcon,
  PackageOpen,
  Route,
  ScrollText,
  TrendingUp,
  TriangleAlert,
  Wallet,
} from "lucide-react";
import { useState } from "react";
import { BarList, RingMeter, StatTile } from "../components/charts";
import { Hl, PageHeader } from "../components/Layout";
import { Card, ErrorState, Segmented, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { cn, humanize, pct, toNumber, usd } from "../lib/format";
import { PACK_STATUS } from "../lib/status";
import type { PackStatus, Stats } from "../lib/types";

const WINDOWS = [
  { value: "24", label: "Last day" },
  { value: "168", label: "Last week" },
  { value: "720", label: "Last 30 days" },
] as const;

type Window = (typeof WINDOWS)[number]["value"];

const ROUTES: Record<string, { label: string; color: string }> = {
  auto_approve: { label: "Approved automatically", color: "#10b981" },
  investigate: { label: "Investigated by agents", color: "#8b5cf6" },
  human_review: { label: "Straight to a person", color: "#ec4899" },
};

/** extractor_invoice -> Extractor · invoice */
function agentLabel(name: string) {
  const [head, ...rest] = name.split("_");
  return rest.length && head === "extractor" ? `Extractor · ${rest.join(" ")}` : humanize(name);
}

export function Monitoring() {
  const [hours, setHours] = useState<Window>("720");
  const q = useQuery({ queryKey: ["stats", Number(hours)], queryFn: () => api.stats(Number(hours)), refetchInterval: 30_000 });

  return (
    <div>
      <PageHeader
        eyebrow="Observability"
        icon={Gauge}
        title={
          <>
            Monitoring <Hl>dashboard</Hl>
          </>
        }
        description="The business numbers: how much runs without a person, what the AI costs and where it is spent."
        actions={<Segmented<Window> ariaLabel="Time window" options={[...WINDOWS]} value={hours} onChange={setHours} />}
      />
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-72 lg:col-span-1" />
          <Skeleton className="h-72 lg:col-span-2" />
        </div>
      ) : (
        <StatsView s={q.data} />
      )}
      <DeeperViews />
    </div>
  );
}

function StatsView({ s }: { s: Stats }) {
  const decided = Object.values(s.routes).reduce((a, b) => a + b, 0);
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <section
          className="glass gradient-border relative flex flex-col items-center overflow-hidden rounded-[28px] p-6 text-center sm:p-8"
          style={{ ["--gb" as string]: "linear-gradient(140deg, #6366f1, #a855f7 50%, #38bdf8)" }}
        >
          <div className="pointer-events-none absolute -top-20 size-72 rounded-full bg-indigo-500/25 blur-3xl" />
          <p className="relative text-xs font-bold tracking-[0.18em] text-indigo-600 uppercase dark:text-indigo-300">Automation rate</p>
          <div className="relative mt-5">
            <RingMeter value={s.automation_rate} size={208} stroke={16} label={<span className="text-5xl">{pct(s.automation_rate)}</span>} sublabel={`of ${decided} routed packs`} colors={["#818cf8", "#38bdf8"]} />
          </div>
          <p className="relative mt-5 max-w-xs text-sm text-ink-2">Packs the match engine approved with nobody involved. Everything else had evidence a person should see.</p>
        </section>

        <Card title="How packs were routed" subtitle="Decided by code; an agent can only make a route stricter" icon={Route}>
          <BarList
            emptyText="No packs routed in this window."
            items={Object.entries(s.routes)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => ({ key: k, label: ROUTES[k]?.label ?? humanize(k), value: v, color: ROUTES[k]?.color }))}
          />
          <div className="mt-6 grid grid-cols-2 gap-3">
            <MiniStat icon={TrendingUp} label="Escalated to a stronger model" value={pct(s.escalation_rate, 1)} />
            <MiniStat icon={TriangleAlert} label="Low-confidence reads" value={pct(s.low_confidence_rate, 1)} />
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Documents read" value={s.documents_extracted} icon={FileStack} gradient="from-cyan-400 to-blue-500" />
        <StatTile label="Documents failed" value={s.documents_failed} icon={FileX2} gradient="from-rose-500 to-red-500" />
        <StatTile label="AI cost per document" display={usd(s.cost_per_document_usd, 4)} icon={CircleDollarSign} gradient="from-emerald-400 to-teal-500" />
        <StatTile label="Total AI spend" display={usd(s.llm_cost_usd, 4)} icon={Wallet} gradient="from-amber-400 to-orange-500" hint="One ledger row per real API call" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="AI cost by agent" subtitle="USD in this window" icon={Bot}>
          <BarList
            color="#818cf8"
            format={(n) => `$${n.toFixed(4)}`}
            emptyText="No model calls in this window."
            items={Object.entries(s.cost_by_agent_usd)
              .map(([k, v]) => ({ key: k, label: agentLabel(k), value: toNumber(v) ?? 0 }))
              .sort((a, b) => b.value - a.value)}
          />
        </Card>
        <Card title="Packs by status" subtitle="Created in this window" icon={PackageOpen}>
          <BarList
            emptyText="No packs in this window."
            items={(Object.entries(s.packs) as [PackStatus, number][])
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => ({ key: k, label: PACK_STATUS[k]?.label ?? k, value: v, color: PACK_STATUS[k]?.color }))}
          />
        </Card>
      </div>
    </div>
  );
}

function MiniStat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-sunk p-3.5 ring-1 ring-line ring-inset">
      <Icon className="size-4 text-ink-3" />
      <p className="mt-2 text-xl font-semibold tracking-tight text-ink tabular">{value}</p>
      <p className="text-xs text-ink-3">{label}</p>
    </div>
  );
}

function DeeperViews() {
  const local = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const views: { name: string; text: string; icon: LucideIcon; gradient: string; href?: string }[] = [
    { name: "Flower", text: "Workers and queues, live", icon: Flower2, gradient: "from-emerald-400 to-teal-500", href: local ? "http://localhost:5555" : undefined },
    { name: "Grafana", text: "Metrics and alerts (monitoring profile)", icon: Activity, gradient: "from-amber-400 to-orange-500", href: local ? "http://localhost:3000" : undefined },
    {
      name: local ? "API docs" : "Cloud Trace",
      text: local ? "Every endpoint, try them live" : "One trace per document",
      icon: ScrollText,
      gradient: "from-sky-400 to-indigo-500",
      href: local ? "http://localhost:8000/docs" : "https://console.cloud.google.com/traces",
    },
  ];
  return (
    <section className="mt-8">
      <h2 className="mb-1 text-lg font-bold tracking-tight text-ink">Deeper views</h2>
      <p className="mb-4 text-sm text-ink-3">The same system, seen from the infrastructure side.</p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {views.map((v) => {
          const body = (
            <>
              <span className={cn("grid size-10 place-items-center rounded-xl bg-linear-to-br text-white shadow-md", v.gradient)}>
                <v.icon className="size-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-ink">{v.name}</span>
                <span className="block text-xs text-ink-3">{v.text}</span>
              </span>
              {v.href && <ArrowUpRight className="size-4 text-ink-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-ink" />}
            </>
          );
          const cls = "glass group flex items-center gap-3 rounded-2xl p-4 transition-transform duration-300 hover:-translate-y-0.5";
          return v.href ? (
            <a key={v.name} href={v.href} target="_blank" rel="noreferrer" className={cls}>
              {body}
            </a>
          ) : (
            <div key={v.name} className={cls}>
              {body}
            </div>
          );
        })}
      </div>
    </section>
  );
}
