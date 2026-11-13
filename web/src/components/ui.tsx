import type { LucideIcon } from "lucide-react";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { animate } from "motion/react";
import { createContext, type ReactNode, useContext, useEffect, useRef } from "react";
import { Link } from "react-router";
import { useScheme } from "../lib/colorScheme";
import { cn } from "../lib/format";
import { packTone } from "../lib/status";
import { type PageTheme, THEMES } from "../lib/themes";

// ------------------------------------------------------------------ page theme
export const PageThemeContext = createContext<PageTheme>(THEMES.aurora);
export const usePageTheme = () => useContext(PageThemeContext);

/** Words painted with a theme's gradient (serif italic unless `plain`), in the right steps for light or dark. */
export function GradientText({
  theme,
  children,
  className,
  plain,
}: {
  theme?: PageTheme;
  children: ReactNode;
  className?: string;
  plain?: boolean;
}) {
  const pageTheme = usePageTheme();
  const t = theme ?? pageTheme;
  const scheme = useScheme();
  return (
    <span className={cn("text-gradient", !plain && "font-serif font-normal italic", className)} style={{ ["--tg" as string]: scheme === "light" ? t.cssLight : t.css }}>
      {children}
    </span>
  );
}

// ------------------------------------------------------------------ surfaces
export function Card({
  children,
  className,
  title,
  subtitle,
  icon: Icon,
  action,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: LucideIcon;
  action?: ReactNode;
}) {
  return (
    <section className={cn("glass min-w-0 rounded-3xl p-5 sm:p-6", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {Icon && <IconBadge icon={Icon} size="sm" />}
            <div className="min-w-0">
              {title && <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>}
              {subtitle && <p className="mt-0.5 text-[13px] text-ink-3">{subtitle}</p>}
            </div>
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function IconBadge({
  icon: Icon,
  size = "md",
  gradient,
  className,
}: {
  icon: LucideIcon;
  size?: "sm" | "md" | "lg";
  gradient?: string;
  className?: string;
}) {
  const theme = usePageTheme();
  const dims = { sm: "size-8 rounded-xl", md: "size-11 rounded-2xl", lg: "size-14 rounded-2xl" }[size];
  const icon = { sm: "size-4", md: "size-5", lg: "size-7" }[size];
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center bg-linear-to-br text-white shadow-lg",
        gradient ?? theme.gradient,
        theme.glow,
        dims,
        className,
      )}
    >
      <Icon className={icon} strokeWidth={2.2} />
    </span>
  );
}

// ------------------------------------------------------------------ pills
export function Pill({
  children,
  className,
  icon: Icon,
  title,
}: {
  children: ReactNode;
  className?: string;
  icon?: LucideIcon;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",
        className ?? "bg-sunk text-ink-2 ring-line",
      )}
    >
      {Icon && <Icon className="size-3.5 shrink-0" strokeWidth={2.4} />}
      <span className="truncate">{children}</span>
    </span>
  );
}

export function StatusPill({ status, live }: { status: string; live?: boolean }) {
  const tone = packTone(status);
  return (
    <Pill className={tone.pill} icon={live ? undefined : tone.icon}>
      {live && (
        <span className="relative mr-0.5 flex size-2">
          <span className="absolute inline-flex size-full animate-ping rounded-full opacity-70" style={{ background: tone.color }} />
          <span className="relative inline-flex size-2 rounded-full" style={{ background: tone.color }} />
        </span>
      )}
      {tone.label}
    </Pill>
  );
}

export function LiveDot({ color = "#10b981" }: { color?: string }) {
  return (
    <span className="relative flex size-2.5">
      <span className="absolute inline-flex size-full animate-ping rounded-full opacity-60" style={{ background: color }} />
      <span className="relative inline-flex size-2.5 rounded-full" style={{ background: color }} />
    </span>
  );
}

// ------------------------------------------------------------------ buttons
type ButtonVariant = "primary" | "ghost" | "subtle" | "danger" | "success";

interface ButtonLook {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  icon?: LucideIcon;
  gradient?: string;
}

function useButtonClass({ variant = "primary", size = "md", gradient }: ButtonLook, className?: string) {
  const theme = usePageTheme();
  const sizes = {
    sm: "h-8 gap-1.5 rounded-xl px-3 text-[13px]",
    md: "h-10 gap-2 rounded-xl px-4 text-sm",
    lg: "h-12 gap-2.5 rounded-2xl px-6 text-[15px]",
  }[size];
  const variants: Record<ButtonVariant, string> = {
    primary: cn("bg-linear-to-r text-white shadow-lg hover:brightness-110", gradient ?? theme.gradient, theme.glow),
    success: "bg-linear-to-r from-emerald-500 to-teal-500 text-white shadow-lg shadow-emerald-500/30 hover:brightness-110",
    danger: "bg-linear-to-r from-rose-500 to-red-500 text-white shadow-lg shadow-rose-500/30 hover:brightness-110",
    ghost: "glass text-ink hover:border-line-strong",
    subtle: "bg-sunk text-ink-2 hover:bg-line hover:text-ink",
  };
  return cn(
    "inline-flex select-none items-center justify-center font-semibold whitespace-nowrap transition-all duration-200 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45",
    sizes,
    variants[variant],
    className,
  );
}

export function Button({
  children,
  variant,
  size,
  icon: Icon,
  loading,
  className,
  gradient,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & ButtonLook & { loading?: boolean }) {
  const cls = useButtonClass({ variant, size, gradient }, className);
  return (
    <button {...rest} disabled={rest.disabled || loading} className={cls}>
      {loading ? <Loader2 className="size-4 animate-spin" /> : Icon && <Icon className="size-4" strokeWidth={2.3} />}
      {children}
    </button>
  );
}

/** A router link that looks like a button. */
export function LinkButton({
  to,
  children,
  variant,
  size,
  icon: Icon,
  gradient,
  className,
}: ButtonLook & { to: string; children: ReactNode; className?: string }) {
  const cls = useButtonClass({ variant, size, gradient }, className);
  return (
    <Link to={to} className={cls}>
      {Icon && <Icon className="size-4" strokeWidth={2.3} />}
      {children}
    </Link>
  );
}

// ------------------------------------------------------------------ segmented control
export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  icon?: LucideIcon;
  /** gradient used when this option is selected */
  gradient?: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  className,
  ariaLabel,
}: {
  options: SegmentOption<T>[];
  value: T | null;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  className?: string;
  ariaLabel: string;
}) {
  const theme = usePageTheme();
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn("inline-flex gap-1 rounded-2xl bg-sunk p-1 ring-1 ring-inset ring-line", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl font-semibold transition-all duration-200",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-[13px]",
              active
                ? cn("bg-linear-to-r text-white shadow-md", o.gradient ?? theme.gradient)
                : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            {o.icon && <o.icon className="size-3.5" strokeWidth={2.4} />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ inputs
export const inputClass =
  "h-11 w-full rounded-xl border border-line bg-surface-2 px-3.5 text-sm text-ink placeholder:text-ink-3 outline-none transition focus:border-violet-400/70 focus:ring-4 focus:ring-violet-500/15";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-semibold text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-ink-3">{hint}</span>}
    </label>
  );
}

// ------------------------------------------------------------------ states
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="relative mb-5">
        <div className="absolute inset-0 scale-150 rounded-full bg-fuchsia-500/20 blur-2xl" />
        <IconBadge icon={Icon} size="lg" className="relative" />
      </div>
      <h3 className="text-lg font-semibold tracking-tight text-ink">{title}</h3>
      {children && <p className="mt-1.5 max-w-md text-sm text-ink-3">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="glass flex flex-col items-start gap-3 rounded-3xl border-rose-500/30! p-6 sm:flex-row sm:items-center">
      <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-rose-500/15 text-rose-500">
        <AlertTriangle className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-ink">Could not load this view</p>
        <p className="mt-0.5 text-sm break-words text-ink-3">
          {message}. Is the API running on port 8000?
        </p>
      </div>
      {onRetry && (
        <Button variant="ghost" size="sm" icon={RefreshCw} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

// ------------------------------------------------------------------ numbers
const wholeNumber = (n: number) => Math.round(n).toLocaleString("en-IN");

/** Counts smoothly from what is on screen to the new value. */
export function AnimatedNumber({ value, format = wholeNumber }: { value: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef(0);
  const formatRef = useRef(format);
  formatRef.current = format;
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const controls = animate(shown.current, value, {
      duration: 0.9,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        shown.current = v;
        node.textContent = formatRef.current(v);
      },
    });
    return () => controls.stop();
  }, [value]);
  return <span ref={ref}>{format(shown.current)}</span>;
}
