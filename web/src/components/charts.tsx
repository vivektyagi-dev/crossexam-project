// Small, dependency-free charts. Bars are thin with a 4px rounded data-end and a square
// baseline; text always wears ink tokens, the coloured mark beside it carries identity.
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { type ReactNode, useId, useState } from "react";
import { Link } from "react-router";
import { cn } from "../lib/format";
import { AnimatedNumber, usePageTheme } from "./ui";

const ease = [0.22, 1, 0.36, 1] as const;

// ------------------------------------------------------------------ stat tile
export function StatTile({
  label,
  value,
  format,
  display,
  hint,
  icon: Icon,
  gradient,
  to,
  emphasis,
}: {
  label: string;
  value?: number;
  format?: (n: number) => string;
  /** pre-formatted value, used instead of the animated number */
  display?: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  gradient?: string;
  to?: string;
  emphasis?: boolean;
}) {
  const theme = usePageTheme();
  const body = (
    <>
      <div
        className={cn(
          "pointer-events-none absolute -top-10 -right-10 size-32 rounded-full bg-linear-to-br opacity-20 blur-2xl transition-opacity duration-500 group-hover:opacity-40",
          gradient ?? theme.gradient,
        )}
      />
      <div className="relative flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-ink-2">{label}</p>
        <span className={cn("grid size-9 shrink-0 place-items-center rounded-xl bg-linear-to-br text-white shadow-md", gradient ?? theme.gradient)}>
          <Icon className="size-4" strokeWidth={2.3} />
        </span>
      </div>
      <p className={cn("relative mt-3 font-semibold tracking-tight text-ink tabular", emphasis ? "text-4xl" : "text-3xl")}>
        {display ?? (value !== undefined ? <AnimatedNumber value={value} format={format} /> : "—")}
      </p>
      {hint && <p className="relative mt-1.5 text-xs text-ink-3">{hint}</p>}
      <div className={cn("absolute inset-x-6 bottom-0 h-px bg-linear-to-r opacity-0 transition-opacity duration-300 group-hover:opacity-100", gradient ?? theme.gradient)} />
    </>
  );
  const cls = "glass group relative block overflow-hidden rounded-3xl p-5 transition-transform duration-300 hover:-translate-y-0.5";
  return to ? (
    <Link to={to} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

// ------------------------------------------------------------------ bar list
export interface BarItem {
  key: string;
  label: string;
  value: number;
  color?: string;
  icon?: LucideIcon;
}

export function BarList({
  items,
  format = (n) => n.toLocaleString("en-IN"),
  color,
  emptyText = "Nothing to show yet.",
}: {
  items: BarItem[];
  format?: (n: number) => string;
  color?: string;
  emptyText?: string;
}) {
  const theme = usePageTheme();
  const [hover, setHover] = useState<string | null>(null);
  const max = Math.max(...items.map((i) => i.value), 0);
  const total = items.reduce((s, i) => s + i.value, 0);
  if (!items.length || max === 0) return <p className="py-8 text-center text-sm text-ink-3">{emptyText}</p>;

  return (
    <ul className="space-y-1">
      {items.map((item, idx) => {
        const share = item.value / max;
        const fill = item.color ?? color ?? theme.accent;
        return (
          <li
            key={item.key}
            onMouseEnter={() => setHover(item.key)}
            onMouseLeave={() => setHover(null)}
            className="relative rounded-xl px-2 py-2 transition-colors hover:bg-sunk"
          >
            <span className="flex min-w-0 items-center gap-2 text-[13px] text-ink-2">
              {item.icon ? (
                <item.icon className="size-3.5 shrink-0 text-ink-3" />
              ) : (
                <span className="size-2 shrink-0 rounded-full" style={{ background: fill }} />
              )}
              <span className="truncate">{item.label}</span>
            </span>
            <span className="mt-1.5 flex items-center">
              <motion.span
                className="block h-2.5 rounded-r-[4px]"
                style={{ background: fill }}
                initial={{ width: 0 }}
                animate={{ width: `calc((100% - 4.5rem) * ${share})` }}
                transition={{ duration: 0.9, ease, delay: idx * 0.04 }}
              />
              <span className="ml-2 text-[13px] font-semibold text-ink tabular">{format(item.value)}</span>
            </span>
            {hover === item.key && (
              <span className="pointer-events-none absolute -top-7 right-2 z-10 rounded-lg bg-ink px-2.5 py-1 text-xs font-medium whitespace-nowrap text-page shadow-xl">
                {item.label}: {format(item.value)} · {total ? Math.round((item.value / total) * 100) : 0}% of total
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ------------------------------------------------------------------ ring meter
export function RingMeter({
  value,
  size = 168,
  stroke = 14,
  label,
  sublabel,
  colors,
}: {
  /** 0..1 */
  value: number;
  size?: number;
  stroke?: number;
  label?: ReactNode;
  sublabel?: ReactNode;
  colors?: [string, string];
}) {
  const theme = usePageTheme();
  const id = `ring${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const [c1, c2] = colors ?? [theme.aurora[0], theme.aurora[1]];
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, value || 0));
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={c1} />
            <stop offset="1" stopColor={c2} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c1} strokeOpacity={0.14} strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${id})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - clamped) }}
          transition={{ duration: 1.2, ease }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-3xl font-semibold tracking-tight text-ink tabular">{label}</div>
          {sublabel && <div className="mt-0.5 text-xs text-ink-3">{sublabel}</div>}
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ stacked bar
export interface Segment {
  key: string;
  label: string;
  value: number;
  color: string;
}

export function StackedBar({ segments, height = 14 }: { segments: Segment[]; height?: number }) {
  const [hover, setHover] = useState<string | null>(null);
  const visible = segments.filter((s) => s.value > 0);
  const total = visible.reduce((s, x) => s + x.value, 0);
  return (
    <div>
      <div className="relative flex w-full gap-[2px] overflow-hidden rounded-[4px] bg-sunk" style={{ height }}>
        {visible.map((s, i) => (
          <motion.div
            key={s.key}
            onMouseEnter={() => setHover(s.key)}
            onMouseLeave={() => setHover(null)}
            className="h-full cursor-default transition-[filter] hover:brightness-125"
            style={{ background: s.color }}
            initial={{ flexGrow: 0 }}
            animate={{ flexGrow: s.value }}
            transition={{ duration: 0.8, ease, delay: i * 0.03 }}
          />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <li
              key={s.key}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-1 text-xs transition-colors",
                hover === s.key ? "bg-sunk text-ink" : "text-ink-2",
              )}
            >
              <span className="size-2.5 rounded-[3px]" style={{ background: s.color }} />
              {s.label}
              <span className="font-semibold text-ink tabular">{s.value}</span>
              {hover === s.key && total > 0 && <span className="text-ink-3">· {Math.round((s.value / total) * 100)}%</span>}
            </li>
          ))}
      </ul>
    </div>
  );
}
