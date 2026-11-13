import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  Braces,
  BrainCircuit,
  CircleDollarSign,
  CloudUpload,
  FileStack,
  Gavel,
  type LucideIcon,
  Scale,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  UserRound,
  Wand2,
} from "lucide-react";
import { motion } from "motion/react";
import { StatTile } from "../components/charts";
import { useAttentionCount } from "../components/Layout";
import { GradientText, IconBadge, LinkButton, Pill } from "../components/ui";
import { api } from "../lib/api";
import { cn, toNumber } from "../lib/format";
import { THEMES, type ThemeKey } from "../lib/themes";

const rise = {
  initial: { opacity: 0, y: 18 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] as const },
};

export function Overview() {
  const stats = useQuery({ queryKey: ["stats", 720], queryFn: () => api.stats(720), refetchInterval: 30_000 });
  const attention = useAttentionCount();
  const s = stats.data;

  return (
    <div className="space-y-10">
      <Hero attention={attention} />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Automation rate"
          value={s ? s.automation_rate * 100 : undefined}
          format={(n) => `${Math.round(n)}%`}
          hint="Packs approved with no person involved, last 30 days"
          icon={Wand2}
          gradient="from-violet-500 to-fuchsia-500"
          to="/monitoring"
        />
        <StatTile
          label="Documents read"
          value={s?.documents_extracted}
          hint="Read and extracted, last 30 days"
          icon={FileStack}
          gradient="from-cyan-400 to-blue-500"
          to="/batches"
        />
        <StatTile
          label="AI cost per document"
          value={s ? (toNumber(s.cost_per_document_usd) ?? 0) : undefined}
          format={(n) => `$${n.toFixed(4)}`}
          hint="Every paid model call is in the cost ledger"
          icon={CircleDollarSign}
          gradient="from-emerald-400 to-teal-500"
          to="/monitoring"
        />
        <StatTile
          label="Waiting for a person"
          value={attention}
          hint="Packs the agents could not settle on their own"
          icon={Gavel}
          gradient="from-amber-400 to-rose-500"
          to="/review"
        />
      </section>

      <Journey />
      <DesignRule />
      <Agents />
      <Guardrails />
    </div>
  );
}

// ------------------------------------------------------------------ hero
function Hero({ attention }: { attention?: number }) {
  return (
    <section className="glass gradient-border relative overflow-hidden rounded-[32px] p-6 sm:p-10 lg:p-12">
      <div className="pointer-events-none absolute -top-32 -right-24 size-[28rem] rounded-full bg-fuchsia-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 left-1/3 size-[26rem] rounded-full bg-violet-500/20 blur-3xl" />
      <div className="relative grid items-center gap-10 lg:grid-cols-[1.15fr_1fr]">
        <div>
          <Pill icon={Sparkles} className="bg-violet-500/12 text-violet-700 ring-violet-500/25 dark:text-violet-200">
            Multi-agent document intelligence
          </Pill>
          <h1 className="mt-5 text-4xl leading-[1.05] font-bold tracking-tight text-ink sm:text-5xl xl:text-6xl">
            Every paper is a{" "}
            <GradientText theme={THEMES.aurora}>witness.</GradientText>
            <br />
            The agents{" "}
            <GradientText theme={THEMES.sunset}>cross‑examine</GradientText>{" "}
            them.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-ink-2 sm:text-lg">
            CrossExam reads supplier paperwork in any format, groups the papers that belong to one shipment, checks
            that they agree with each other, with the purchase order and with what the warehouse received, and hands
            people only the cases that need them, with the evidence and a proposed fix.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <LinkButton to="/upload" size="lg" icon={CloudUpload} gradient="from-violet-500 via-fuchsia-500 to-pink-500">
              Upload a batch
            </LinkButton>
            <LinkButton to="/review" size="lg" variant="ghost" icon={Gavel}>
              Open review queue
              {!!attention && (
                <span className="ml-1 rounded-full bg-linear-to-r from-amber-400 to-rose-500 px-2 py-0.5 text-xs font-bold text-white">
                  {attention}
                </span>
              )}
            </LinkButton>
          </div>
          <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-ink-3">
            {["LangChain v1 agents", "Celery + Redis", "PostgreSQL + pgvector", "FastAPI", "Google Cloud Run"].map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-linear-to-r from-violet-400 to-amber-300" />
                {t}
              </span>
            ))}
          </div>
        </div>
        <EvidenceStack />
      </div>
    </section>
  );
}

/** An illustration of the short-shipment case: three papers disagree, the verdict explains why. */
function EvidenceStack() {
  // Laid out so no paper hides another: two side by side, the warehouse's receipt below them.
  const papers = [
    { title: "Invoice", sub: "billed", qty: "500 cartons", tint: "from-violet-500 to-fuchsia-500", rotate: -5, left: "0%", top: 0 },
    { title: "Lorry receipt", sub: "transporter carried", qty: "488 cartons", tint: "from-amber-400 to-orange-500", rotate: 4, left: "52%", top: 28 },
    { title: "Goods receipt", sub: "warehouse received", qty: "488 cartons", tint: "from-cyan-400 to-blue-500", rotate: -2, left: "26%", top: 162 },
  ];
  return (
    <div className="relative mx-auto h-[370px] w-full max-w-[420px]" aria-hidden>
      {papers.map((p, i) => (
        <motion.div
          key={p.title}
          className="glass absolute w-[48%] rounded-2xl bg-surface-2! p-4"
          style={{ left: p.left, top: p.top }}
          initial={{ opacity: 0, y: 30, rotate: 0 }}
          animate={{ opacity: 1, y: [0, -7, 0], rotate: p.rotate }}
          transition={{
            opacity: { duration: 0.6, delay: 0.15 * i },
            rotate: { duration: 0.8, delay: 0.15 * i, ease: [0.22, 1, 0.36, 1] },
            y: { duration: 5 + i, repeat: Infinity, ease: "easeInOut", delay: 0.15 * i },
          }}
        >
          <div className="flex items-center gap-2.5">
            <span className={cn("grid size-8 place-items-center rounded-lg bg-linear-to-br text-white", p.tint)}>
              <FileStack className="size-4" />
            </span>
            <div>
              <p className="text-sm font-semibold text-ink">{p.title}</p>
              <p className="text-[11px] text-ink-3">{p.sub}</p>
            </div>
          </div>
          <div className="mt-3 h-1.5 w-3/4 rounded-full bg-line" />
          <p className="mt-2.5 text-xl font-bold tracking-tight text-ink tabular">{p.qty}</p>
        </motion.div>
      ))}
      <motion.div
        className="absolute right-0 bottom-0 left-0 mx-auto w-[290px] rounded-2xl bg-linear-to-r from-rose-500 via-fuchsia-500 to-violet-500 p-[1px] shadow-2xl shadow-fuchsia-500/30"
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ delay: 0.8, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="flex items-center gap-3 rounded-2xl bg-page/90 p-3.5 backdrop-blur-xl">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-linear-to-br from-rose-500 to-fuchsia-500 text-white">
            <ScanSearch className="size-5" />
          </span>
          <div>
            <p className="text-sm font-semibold text-ink">Short shipment: 12 cartons</p>
            <p className="text-xs text-ink-3">Pay for 488 · debit note proposed</p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

// ------------------------------------------------------------------ the journey of a paper
type Who = "ai" | "code" | "person";

const WHO: Record<Who, { label: string; icon: LucideIcon; cls: string }> = {
  ai: { label: "AI", icon: Sparkles, cls: "bg-fuchsia-500/12 text-fuchsia-700 ring-fuchsia-500/25 dark:text-fuchsia-200" },
  code: { label: "Code", icon: Braces, cls: "bg-emerald-500/12 text-emerald-700 ring-emerald-500/25 dark:text-emerald-200" },
  person: { label: "Person", icon: UserRound, cls: "bg-amber-500/12 text-amber-700 ring-amber-500/25 dark:text-amber-200" },
};

const PHASES: { name: string; theme: ThemeKey; steps: { title: string; text: string; who: Who[] }[] }[] = [
  {
    name: "Intake",
    theme: "orchid",
    steps: [
      { title: "Upload and dedupe", text: "A file hash means the same file is never read twice.", who: ["code"] },
      { title: "Read any format", text: "Vision per page for scans; Excel and GST JSON read with no AI.", who: ["ai", "code"] },
    ],
  },
  {
    name: "Understand",
    theme: "ocean",
    steps: [
      { title: "Classifier agent", text: "Works out what each page is and splits bundles into documents.", who: ["ai"] },
      { title: "Extractor agents", text: "One per document family, filling a strict form; rule checks escalate once.", who: ["ai", "code"] },
    ],
  },
  {
    name: "Reconcile",
    theme: "sunset",
    steps: [
      { title: "Group into packs", text: "Papers that belong to one shipment are joined on strong keys.", who: ["code"] },
      { title: "Match engine", text: "Totals, tolerances, payable amount and debit note: exact and explainable.", who: ["code"] },
      { title: "Supervisor + reconciler", text: "Route each pack: approve, investigate, or hand to a person.", who: ["ai"] },
    ],
  },
  {
    name: "Resolve",
    theme: "lagoon",
    steps: [
      { title: "Exception agent", text: "Investigates with tools and proposes a fix and a supplier email.", who: ["ai"] },
      { title: "Human approval", text: "Nothing is written until a person approves, edits or rejects.", who: ["person"] },
      { title: "ERP export", text: "Each invoice is exported exactly once. No agent can trigger it.", who: ["code"] },
    ],
  },
];

function Journey() {
  return (
    <section>
      <SectionHeading eyebrow="How it works" title="The journey of a paper" icon={BrainCircuit} theme="ocean">
        Four phases, two kinds of worker. AI reads and investigates; plain code does every sum and every money decision.
      </SectionHeading>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {PHASES.map((phase, i) => {
          const t = THEMES[phase.theme];
          return (
            <motion.div key={phase.name} {...rise} transition={{ ...rise.transition, delay: i * 0.08 }} className="relative">
              <div className="glass h-full rounded-3xl p-5">
                <div className="flex items-center gap-3">
                  <span className={cn("grid size-9 place-items-center rounded-xl bg-linear-to-br text-sm font-bold text-white shadow-lg", t.gradient, t.glow)}>
                    {i + 1}
                  </span>
                  <h3 className="text-lg font-semibold tracking-tight text-ink">{phase.name}</h3>
                </div>
                <div className={cn("mt-4 h-[3px] rounded-full bg-linear-to-r opacity-80", t.gradient)} />
                <ol className="mt-4 space-y-3">
                  {phase.steps.map((step) => (
                    <li key={step.title} className="rounded-2xl bg-sunk p-3.5 ring-1 ring-line ring-inset">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-ink">{step.title}</p>
                        <span className="flex gap-1">
                          {step.who.map((w) => (
                            <Pill key={w} icon={WHO[w].icon} className={cn(WHO[w].cls, "px-2 py-0.5 text-[11px]")}>
                              {WHO[w].label}
                            </Pill>
                          ))}
                        </span>
                      </div>
                      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-3">{step.text}</p>
                    </li>
                  ))}
                </ol>
              </div>
              {i < PHASES.length - 1 && (
                <div className="absolute top-1/2 -right-4 z-10 hidden h-px w-4 overflow-visible bg-line-strong xl:block">
                  <span className={cn("travel-dot absolute -top-[3px] size-[7px] rounded-full bg-linear-to-r", t.gradient)} />
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ the one design rule
function DesignRule() {
  const ai = ["Reads documents in any format", "Splits mixed bundles", "Investigates what does not add up", "Drafts the supplier email"];
  const code = ["Totals, tax and tolerances", "Matching against PO and GRN", "Every money decision", "ERP export, exactly once"];
  return (
    <motion.section {...rise} className="glass gradient-border relative overflow-hidden rounded-[32px] p-6 sm:p-10" style={{ ["--gb" as string]: "linear-gradient(120deg, #d946ef, #8b5cf6 40%, #10b981)" }}>
      <div className="text-center">
        <p className="text-xs font-bold tracking-[0.18em] text-violet-600 uppercase dark:text-violet-300">The one design rule</p>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
          AI investigates. <GradientText theme={THEMES.lagoon}>Code decides money.</GradientText>
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-[15px] text-ink-2">
          Agents call the match engine as a tool, so totals are exact, free and explainable. An agent can make a route
          stricter, never looser.
        </p>
      </div>
      <div className="relative mt-8 grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-center">
        <RuleColumn title="What the AI does" icon={Bot} gradient="from-fuchsia-500 to-violet-500" items={ai} />
        <div className="mx-auto grid size-16 place-items-center rounded-full bg-linear-to-br from-violet-500 to-emerald-500 text-white shadow-xl shadow-violet-500/30">
          <Scale className="size-7" />
        </div>
        <RuleColumn title="What plain code does" icon={Braces} gradient="from-emerald-500 to-teal-500" items={code} />
      </div>
    </motion.section>
  );
}

function RuleColumn({ title, icon, gradient, items }: { title: string; icon: LucideIcon; gradient: string; items: string[] }) {
  return (
    <div className="rounded-3xl bg-sunk p-5 ring-1 ring-line ring-inset">
      <div className="flex items-center gap-3">
        <IconBadge icon={icon} size="sm" gradient={gradient} />
        <h3 className="font-semibold text-ink">{title}</h3>
      </div>
      <ul className="mt-4 space-y-2.5">
        {items.map((item) => (
          <li key={item} className="flex items-center gap-2.5 text-sm text-ink-2">
            <span className={cn("size-1.5 shrink-0 rounded-full bg-linear-to-r", gradient)} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------ agents
const AGENTS: { name: string; tier: string; tools: string[]; gated?: string[]; output: string; gradient: string }[] = [
  {
    name: "Classifier",
    tier: "small model",
    tools: ["page_text", "page_image", "doc_type_catalog"],
    output: "Segments per document; code repairs page coverage",
    gradient: "from-sky-400 to-indigo-500",
  },
  {
    name: "Extractors",
    tier: "small, escalates to strong",
    tools: ["hsn_lookup", "gstin_check", "unit_convert"],
    output: "A strict Pydantic form per document type",
    gradient: "from-violet-500 to-fuchsia-500",
  },
  {
    name: "Supervisor",
    tier: "small model",
    tools: ["run_reconciler", "pack_overview", "match_engine"],
    output: "Route: auto-approve, investigate or human review",
    gradient: "from-fuchsia-500 to-pink-500",
  },
  {
    name: "Reconciler",
    tier: "mid model",
    tools: ["pack_overview", "find_related_docs", "match_engine", "tolerance_rules"],
    output: "Report and proposed links, verified by code",
    gradient: "from-amber-400 to-orange-500",
  },
  {
    name: "Exception resolver",
    tier: "strong model",
    tools: ["po_grn_lookup", "supplier_history", "similar_cases", "duplicate_search", "match_engine"],
    gated: ["propose_fix", "draft_supplier_email"],
    output: "A finding; write actions wait for a person",
    gradient: "from-rose-500 to-red-500",
  },
];

function Agents() {
  return (
    <section>
      <SectionHeading eyebrow="The cast" title="Meet the agents" icon={Bot} theme="aurora">
        Every agent is a LangChain v1 <code className="font-mono text-[13px]">create_agent</code>, wrapped in the same
        middleware stack. Write tools are gated: they pause the agent until a person decides.
      </SectionHeading>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {AGENTS.map((a, i) => (
          <motion.div
            key={a.name}
            {...rise}
            transition={{ ...rise.transition, delay: i * 0.06 }}
            className="glass group relative flex flex-col overflow-hidden rounded-3xl p-5 transition-transform duration-300 hover:-translate-y-1"
          >
            <div className={cn("absolute inset-x-0 top-0 h-1 bg-linear-to-r", a.gradient)} />
            <div className={cn("pointer-events-none absolute -top-16 -right-16 size-36 rounded-full bg-linear-to-br opacity-15 blur-2xl transition-opacity group-hover:opacity-30", a.gradient)} />
            <IconBadge icon={Bot} size="sm" gradient={a.gradient} />
            <h3 className="mt-4 text-base font-semibold text-ink">{a.name}</h3>
            <p className="text-xs font-medium text-ink-3">{a.tier}</p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {a.tools.map((t) => (
                <span key={t} className="rounded-md bg-sunk px-1.5 py-0.5 font-mono text-[11px] text-ink-2 ring-1 ring-line ring-inset">
                  {t}
                </span>
              ))}
              {a.gated?.map((t) => (
                <span
                  key={t}
                  title="Gated: waits for human approval"
                  className="flex items-center gap-1 rounded-md bg-amber-500/12 px-1.5 py-0.5 font-mono text-[11px] text-amber-800 ring-1 ring-amber-500/30 ring-inset dark:text-amber-200"
                >
                  <ShieldCheck className="size-3" />
                  {t}
                </span>
              ))}
            </div>
            <p className="mt-auto pt-4 text-[13px] leading-relaxed text-ink-2">{a.output}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ guardrails
const GUARDRAILS: { name: string; text: string; custom?: boolean }[] = [
  { name: "PII masking", text: "Bank account and IFSC numbers masked before any model sees them." },
  { name: "Injection guard", text: "Instruction-like lines removed from documents and tool results.", custom: true },
  { name: "Call limits", text: "Model and tool call caps stop a confused agent." },
  { name: "Summarisation", text: "Long investigations keep fitting in context." },
  { name: "Fallback + retry", text: "A backup model and visible retries." },
  { name: "Shared rate limit", text: "One Redis token bucket for every worker.", custom: true },
  { name: "Cost ledger", text: "One row per real API call: never pay twice.", custom: true },
  { name: "Confidence gate", text: "Low confidence goes to a person.", custom: true },
  { name: "Human in the loop", text: "Write tools wait for approval, then resume." },
];

function Guardrails() {
  return (
    <section>
      <SectionHeading eyebrow="Middleware" title="Nine guardrails on every model call" icon={ShieldCheck} theme="lagoon">
        Outermost first. Built-in LangChain middleware plus four custom layers written for this project.
      </SectionHeading>
      <motion.ol {...rise} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {GUARDRAILS.map((g, i) => (
          <li key={g.name} className="glass flex gap-4 rounded-2xl p-4">
            <span
              className="grid size-10 shrink-0 place-items-center rounded-xl text-sm font-bold text-white shadow-md"
              style={{ background: `linear-gradient(135deg, hsl(${160 + i * 18} 80% 50%), hsl(${190 + i * 18} 85% 55%))` }}
            >
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
                {g.name}
                <span className={cn("rounded-full px-1.5 py-px text-[10px] font-bold tracking-wide uppercase", g.custom ? "bg-fuchsia-500/12 text-fuchsia-700 dark:text-fuchsia-300" : "bg-sunk text-ink-3")}>
                  {g.custom ? "custom" : "built-in"}
                </span>
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-3">{g.text}</p>
            </div>
          </li>
        ))}
      </motion.ol>
      <div className="mt-6 flex justify-center">
        <LinkButton to="/upload" variant="ghost" icon={ArrowRight}>
          Try it: upload the demo batch
        </LinkButton>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ helpers
function SectionHeading({
  eyebrow,
  title,
  icon,
  theme,
  children,
}: {
  eyebrow: string;
  title: string;
  icon: LucideIcon;
  theme: ThemeKey;
  children?: React.ReactNode;
}) {
  const t = THEMES[theme];
  return (
    <div className="mb-5 flex items-start gap-4">
      <IconBadge icon={icon} gradient={t.gradient} />
      <div>
        <p className={cn("text-xs font-bold tracking-[0.18em] uppercase", t.eyebrow)}>{eyebrow}</p>
        <h2 className="mt-0.5 text-2xl font-bold tracking-tight text-ink">{title}</h2>
        {children && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-ink-2">{children}</p>}
      </div>
    </div>
  );
}
