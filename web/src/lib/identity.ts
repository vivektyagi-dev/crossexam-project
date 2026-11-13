// Demo sign-in: the name and role travel to the API as X-User / X-Role headers.
// On Google Cloud, Identity-Aware Proxy supplies the real identity.
import { useSyncExternalStore } from "react";
import type { Role } from "./types";

export interface Identity {
  name: string;
  role: Role;
}

export const ROLE_LABELS: Record<Role, string> = {
  ap_executive: "AP executive",
  finance_manager: "Finance manager",
};

const KEY = "crossexam.identity";
const listeners = new Set<() => void>();

function load(): Identity {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (saved && typeof saved.name === "string" && saved.role in ROLE_LABELS) return saved;
  } catch {
    /* storage blocked or corrupt: fall back to the demo user */
  }
  return { name: "priya", role: "ap_executive" };
}

let current = load();

export function getIdentity(): Identity {
  return current;
}

export function setIdentity(next: Partial<Identity>): void {
  current = { ...current, ...next };
  try {
    localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    /* keep it for this tab only */
  }
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useIdentity(): Identity {
  return useSyncExternalStore(subscribe, getIdentity);
}
