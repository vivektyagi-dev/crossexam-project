import { useSyncExternalStore } from "react";

export type Scheme = "dark" | "light";

const KEY = "crossexam.theme";
const listeners = new Set<() => void>();

function read(): Scheme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setScheme(next: Scheme): void {
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* remembered for this tab only */
  }
  listeners.forEach((fn) => fn());
}

export function useScheme(): Scheme {
  return useSyncExternalStore((fn) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }, read);
}
