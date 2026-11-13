import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CloudUpload,
  FileOutput,
  Gauge,
  Gavel,
  type LucideIcon,
  Menu,
  Moon,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { type ReactNode, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { toast } from "sonner";
import { api } from "../lib/api";
import { setScheme, useScheme } from "../lib/colorScheme";
import { cn, initials } from "../lib/format";
import { ROLE_LABELS, setIdentity, useIdentity } from "../lib/identity";
import { ATTENTION } from "../lib/status";
import { THEMES, type ThemeKey, themeForPath } from "../lib/themes";
import type { Role } from "../lib/types";
import { GradientText, PageThemeContext, Segmented, usePageTheme } from "./ui";

const NAV: { to: string; label: string; icon: LucideIcon; theme: ThemeKey; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: Sparkles, theme: "aurora", end: true },
  { to: "/upload", label: "Upload", icon: CloudUpload, theme: "orchid" },
  { to: "/batches", label: "Live batches", icon: Activity, theme: "ocean" },
  { to: "/review", label: "Review queue", icon: Gavel, theme: "sunset" },
  { to: "/export", label: "Export to ERP", icon: FileOutput, theme: "lagoon" },
  { to: "/monitoring", label: "Monitoring", icon: Gauge, theme: "nebula" },
];

export function useAttentionCount() {
  return useQuery({
    queryKey: ["packs", ATTENTION],
    queryFn: () => api.packs(ATTENTION),
    refetchInterval: 15_000,
    select: (packs) => packs.length,
  }).data;
}

// ------------------------------------------------------------------ layout
export function Layout() {
  const { pathname } = useLocation();
  const theme = THEMES[themeForPath(pathname)];
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo({ top: 0 });
  }, [pathname]);

  return (
    <PageThemeContext.Provider value={theme}>
      <Aurora colors={theme.aurora} />
      <div className="relative z-10 flex min-h-dvh">
        <aside className="sticky top-0 hidden h-dvh w-[17.5rem] shrink-0 p-4 lg:block">
          <SidebarContent />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <MobileBar onMenu={() => setMenuOpen(true)} />
          <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 pt-6 pb-20 sm:px-6 lg:px-10 lg:pt-10">
            <motion.div
              key={pathname.split("/")[1] ?? ""}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            >
              <Outlet />
            </motion.div>
          </main>
        </div>
      </div>

      <AnimatePresence>
        {menuOpen && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMenuOpen(false)}
            />
            <motion.aside
              className="fixed inset-y-0 left-0 z-50 w-[17.5rem] p-3 lg:hidden"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 300 }}
            >
              <SidebarContent onClose={() => setMenuOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </PageThemeContext.Provider>
  );
}

function Aurora({ colors }: { colors: [string, string, string] }) {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div className="aurora-blob" style={{ backgroundColor: colors[0], width: "46vw", height: "46vw", top: "-20vw", left: "-8vw" }} />
      <div className="aurora-blob" style={{ backgroundColor: colors[1], width: "38vw", height: "38vw", top: "8vh", right: "-14vw" }} />
      <div className="aurora-blob" style={{ backgroundColor: colors[2], width: "34vw", height: "34vw", bottom: "-18vw", left: "28vw" }} />
      <div className="grid-bg absolute inset-0" />
    </div>
  );
}

// ------------------------------------------------------------------ sidebar
function Logo() {
  return (
    <Link to="/" className="group flex items-center gap-3">
      <span className="relative grid size-11 place-items-center rounded-2xl bg-linear-to-br from-violet-500 via-fuchsia-500 to-amber-400 shadow-lg shadow-fuchsia-500/30 transition-transform duration-300 group-hover:rotate-[-6deg]">
        <img src="/favicon.svg" alt="" className="size-11 rounded-2xl" />
      </span>
      <span>
        <span className="block text-lg leading-tight font-bold tracking-tight text-ink">
          Cross<GradientText theme={THEMES.aurora} plain>
            Exam
          </GradientText>
        </span>
        <span className="block font-serif text-[13px] leading-tight text-ink-3 italic">every paper is a witness</span>
      </span>
    </Link>
  );
}

function SidebarContent({ onClose }: { onClose?: () => void }) {
  const attention = useAttentionCount();
  return (
    <div className="glass flex h-full flex-col rounded-[28px] p-4">
      <div className="flex items-center justify-between px-1 pt-1">
        <Logo />
        {onClose && (
          <button onClick={onClose} className="grid size-9 place-items-center rounded-xl text-ink-2 hover:bg-sunk" aria-label="Close menu">
            <X className="size-5" />
          </button>
        )}
      </div>

      <nav className="mt-8 space-y-1" aria-label="Main">
        <p className="mb-2 px-3 text-[11px] font-bold tracking-[0.14em] text-ink-3 uppercase">Workspace</p>
        {NAV.map((item) => (
          <NavItem key={item.to} {...item} badge={item.to === "/review" ? attention : undefined} />
        ))}
      </nav>

      <div className="mt-auto space-y-3">
        <IdentityCard />
        <SchemeToggle />
      </div>
    </div>
  );
}

function NavItem({
  to,
  label,
  icon: Icon,
  theme,
  end,
  badge,
}: {
  to: string;
  label: string;
  icon: LucideIcon;
  theme: ThemeKey;
  end?: boolean;
  badge?: number;
}) {
  const t = THEMES[theme];
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-semibold transition-all duration-200",
          isActive ? "bg-surface-2 text-ink shadow-sm ring-1 ring-line" : "text-ink-2 hover:bg-sunk hover:text-ink",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span
              layoutId="nav-indicator"
              className={cn("absolute top-2 bottom-2 -left-4 w-1 rounded-r-full bg-linear-to-b", t.gradient)}
            />
          )}
          <span
            className={cn(
              "grid size-8 place-items-center rounded-xl transition-all duration-300",
              isActive ? cn("bg-linear-to-br text-white shadow-md", t.gradient, t.glow) : "bg-sunk text-ink-3 group-hover:text-ink",
            )}
          >
            <Icon className="size-4" strokeWidth={2.3} />
          </span>
          <span className="flex-1">{label}</span>
          {!!badge && (
            <span className="grid h-5 min-w-5 place-items-center rounded-full bg-linear-to-r from-amber-400 to-rose-500 px-1.5 text-[11px] font-bold text-white shadow-md shadow-rose-500/30">
              {badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

function IdentityCard() {
  const { name, role } = useIdentity();
  return (
    <div className="rounded-2xl bg-sunk p-3 ring-1 ring-line ring-inset">
      <div className="flex items-center gap-2.5">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-linear-to-br from-sky-400 to-violet-500 text-xs font-bold text-white">
          {initials(name || "?")}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold tracking-[0.12em] text-ink-3 uppercase">Signed in as</p>
          <input
            value={name}
            onChange={(e) => setIdentity({ name: e.target.value })}
            aria-label="Your name"
            className="w-full truncate bg-transparent text-sm font-semibold text-ink outline-none"
          />
        </div>
      </div>
      <Segmented<Role>
        ariaLabel="Role"
        size="sm"
        className="mt-3 flex w-full"
        value={role}
        onChange={(r) => {
          setIdentity({ role: r });
          toast.success(`Now acting as ${ROLE_LABELS[r]}`);
        }}
        options={[
          { value: "ap_executive", label: "AP executive", gradient: "from-sky-500 to-indigo-500" },
          { value: "finance_manager", label: "Finance mgr", gradient: "from-amber-500 to-rose-500" },
        ]}
      />
      <p className="mt-2.5 text-[11px] leading-snug text-ink-3">
        Demo sign-in. On Google Cloud, Identity-Aware Proxy supplies the real identity.
      </p>
    </div>
  );
}

function SchemeToggle() {
  const scheme = useScheme();
  const next = scheme === "dark" ? "light" : "dark";
  return (
    <button
      onClick={() => setScheme(next)}
      className="flex w-full items-center justify-between rounded-2xl px-3 py-2 text-[13px] font-semibold text-ink-2 transition hover:bg-sunk hover:text-ink"
    >
      <span>{scheme === "dark" ? "Dark" : "Light"} theme</span>
      <span className="relative flex h-7 w-12 items-center rounded-full bg-sunk p-0.5 ring-1 ring-line ring-inset">
        <motion.span
          layout
          transition={{ type: "spring", stiffness: 500, damping: 32 }}
          className={cn(
            "grid size-6 place-items-center rounded-full text-white shadow",
            scheme === "dark" ? "ml-auto bg-linear-to-br from-indigo-500 to-violet-600" : "bg-linear-to-br from-amber-400 to-orange-500",
          )}
        >
          {scheme === "dark" ? <Moon className="size-3.5" /> : <Sun className="size-3.5" />}
        </motion.span>
      </span>
    </button>
  );
}

function MobileBar({ onMenu }: { onMenu: () => void }) {
  const attention = useAttentionCount();
  return (
    <div className="sticky top-0 z-30 p-3 lg:hidden">
      <div className="glass flex items-center justify-between rounded-2xl px-3 py-2">
        <Logo />
        <div className="flex items-center gap-2">
          {!!attention && (
            <Link
              to="/review"
              className="rounded-full bg-linear-to-r from-amber-400 to-rose-500 px-2.5 py-1 text-xs font-bold text-white"
            >
              {attention} to review
            </Link>
          )}
          <button onClick={onMenu} className="grid size-10 place-items-center rounded-xl text-ink hover:bg-sunk" aria-label="Open menu">
            <Menu className="size-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ page header
/** The highlighted word in a page title: serif italic in the page's gradient. */
export function Hl({ children }: { children: ReactNode }) {
  return <GradientText className="pr-1 text-[1.12em]">{children}</GradientText>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  icon: Icon,
  actions,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  icon: LucideIcon;
  actions?: ReactNode;
}) {
  const theme = usePageTheme();
  return (
    <header className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex min-w-0 items-start gap-4">
        <span className={cn("mt-1 hidden size-14 shrink-0 place-items-center rounded-[20px] bg-linear-to-br text-white shadow-xl sm:grid", theme.gradient, theme.glow)}>
          <Icon className="size-7" strokeWidth={2} />
        </span>
        <div className="min-w-0">
          <p className={cn("text-xs font-bold tracking-[0.18em] uppercase", theme.eyebrow)}>{eyebrow}</p>
          <h1 className="mt-1.5 text-3xl leading-tight font-bold tracking-tight text-ink sm:text-[2.6rem]">{title}</h1>
          {description && <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
