// Every page has its own colour story. The aurora behind the page drifts to the
// page's colours as you navigate, so each screen feels distinct but part of one family.

export interface PageTheme {
  /** Tailwind gradient stops for buttons, icon badges and bars */
  gradient: string;
  /** CSS gradient for gradient text and gradient borders, on the dark page */
  css: string;
  /** the same gradient in deeper steps, legible on the light page */
  cssLight: string;
  /** three aurora blob colours */
  aurora: [string, string, string];
  /** single-series chart colour */
  accent: string;
  /** small uppercase label above the page title */
  eyebrow: string;
  /** soft glow behind icon badges */
  glow: string;
}

export const THEMES = {
  aurora: {
    gradient: "from-violet-500 via-fuchsia-500 to-amber-400",
    css: "linear-gradient(100deg, #a78bfa, #f0abfc 45%, #fcd34d)",
    cssLight: "linear-gradient(100deg, #7c3aed, #c026d3 50%, #ea580c)",
    aurora: ["#7c3aed", "#db2777", "#f59e0b"],
    accent: "#a855f7",
    eyebrow: "text-violet-600 dark:text-violet-300",
    glow: "shadow-fuchsia-500/40",
  },
  orchid: {
    gradient: "from-fuchsia-500 via-purple-500 to-indigo-500",
    css: "linear-gradient(100deg, #f0abfc, #c4b5fd 50%, #a5b4fc)",
    cssLight: "linear-gradient(100deg, #c026d3, #7c3aed 50%, #4f46e5)",
    aurora: ["#c026d3", "#7c3aed", "#4f46e5"],
    accent: "#d946ef",
    eyebrow: "text-fuchsia-600 dark:text-fuchsia-300",
    glow: "shadow-fuchsia-500/40",
  },
  ocean: {
    gradient: "from-cyan-400 via-sky-500 to-indigo-500",
    css: "linear-gradient(100deg, #67e8f9, #7dd3fc 45%, #a5b4fc)",
    cssLight: "linear-gradient(100deg, #0891b2, #0284c7 50%, #4f46e5)",
    aurora: ["#0891b2", "#2563eb", "#6366f1"],
    accent: "#06b6d4",
    eyebrow: "text-cyan-700 dark:text-cyan-300",
    glow: "shadow-cyan-500/40",
  },
  sunset: {
    gradient: "from-amber-400 via-orange-500 to-rose-500",
    css: "linear-gradient(100deg, #fcd34d, #fdba74 40%, #fda4af)",
    cssLight: "linear-gradient(100deg, #d97706, #ea580c 45%, #e11d48)",
    aurora: ["#f59e0b", "#e11d48", "#c026d3"],
    accent: "#f43f5e",
    eyebrow: "text-orange-600 dark:text-amber-300",
    glow: "shadow-orange-500/40",
  },
  lagoon: {
    gradient: "from-emerald-400 via-teal-500 to-cyan-500",
    css: "linear-gradient(100deg, #6ee7b7, #5eead4 45%, #67e8f9)",
    cssLight: "linear-gradient(100deg, #059669, #0d9488 50%, #0891b2)",
    aurora: ["#059669", "#0d9488", "#0284c7"],
    accent: "#10b981",
    eyebrow: "text-emerald-700 dark:text-emerald-300",
    glow: "shadow-emerald-500/40",
  },
  nebula: {
    gradient: "from-indigo-500 via-violet-500 to-sky-400",
    css: "linear-gradient(100deg, #a5b4fc, #c4b5fd 45%, #7dd3fc)",
    cssLight: "linear-gradient(100deg, #4f46e5, #7c3aed 50%, #0284c7)",
    aurora: ["#4f46e5", "#9333ea", "#0ea5e9"],
    accent: "#6366f1",
    eyebrow: "text-indigo-600 dark:text-indigo-300",
    glow: "shadow-indigo-500/40",
  },
} satisfies Record<string, PageTheme>;

export type ThemeKey = keyof typeof THEMES;

/** Which colour story belongs to which route. */
export function themeForPath(pathname: string): ThemeKey {
  if (pathname.startsWith("/upload")) return "orchid";
  if (pathname.startsWith("/batches")) return "ocean";
  if (pathname.startsWith("/review")) return "sunset";
  if (pathname.startsWith("/export")) return "lagoon";
  if (pathname.startsWith("/monitoring")) return "nebula";
  return "aurora";
}
