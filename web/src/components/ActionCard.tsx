import { Ban, CircleCheckBig, Crown, HandCoins, Mail, PencilLine, ShieldAlert, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { humanize, rupees } from "../lib/format";
import type { PendingAction, Role } from "../lib/types";
import { Callout, JsonView } from "./DocumentViewer";
import { inputClass, Pill, Segmented } from "./ui";

export type DraftType = "approve" | "edit" | "reject";

export interface Draft {
  type: DraftType | null;
  json: string;
  message: string;
}

/** Arguments the person sees and may edit; keys starting with "_" are notes from code. */
export function visibleArgs(args: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(args).filter(([k]) => !k.startsWith("_")));
}

export function newDraft(action: PendingAction): Draft {
  return { type: null, json: JSON.stringify(visibleArgs(action.args), null, 2), message: "" };
}

export function jsonError(draft: Draft): string | null {
  if (draft.type !== "edit") return null;
  try {
    const parsed = JSON.parse(draft.json);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? null : "The action must be a JSON object.";
  } catch {
    return "That is not valid JSON.";
  }
}

const TOOL_ICON: Record<string, typeof Mail> = { draft_supplier_email: Mail, propose_fix: HandCoins };

export function ActionCard({
  action,
  draft,
  onChange,
  role,
  index,
}: {
  action: PendingAction;
  draft: Draft;
  onChange: (d: Draft) => void;
  role: Role;
  index: number;
}) {
  const Icon = TOOL_ICON[action.tool] ?? Wrench;
  const shown = visibleArgs(action.args);
  const warning = typeof action.args._warning === "string" ? action.args._warning : null;
  const needsManager = action.requires_role === "finance_manager";
  const roleBlocked = needsManager && role !== "finance_manager" && (draft.type === "approve" || draft.type === "edit");
  const error = jsonError(draft);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08 }}
      className="glass gradient-border relative overflow-hidden rounded-3xl p-5 sm:p-6"
      style={{ ["--gb" as string]: "linear-gradient(120deg, #f59e0b, #f43f5e 50%, #d946ef)" }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-linear-to-br from-amber-400 to-rose-500 text-white shadow-lg shadow-rose-500/30">
            <Icon className="size-5" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-bold tracking-[0.14em] text-ink-3 uppercase">Action {index + 1} · held for you</p>
            <h3 className="text-base font-semibold text-ink">{humanize(action.tool)}</h3>
            <p className="mt-0.5 text-sm text-ink-2">{action.description}</p>
          </div>
        </div>
        {needsManager && (
          <Pill icon={Crown} className="bg-amber-500/12 text-amber-800 ring-amber-500/30 dark:text-amber-200">
            Needs the finance manager
          </Pill>
        )}
      </div>

      {warning && (
        <div className="mt-4">
          <Callout tone="red" icon={ShieldAlert}>
            {warning}
          </Callout>
        </div>
      )}

      <div className="mt-5">
        {draft.type === "edit" ? (
          <div>
            <textarea
              value={draft.json}
              onChange={(e) => onChange({ ...draft, json: e.target.value })}
              spellCheck={false}
              rows={Math.min(18, draft.json.split("\n").length + 1)}
              aria-label="Edit the action as JSON"
              className="w-full rounded-xl bg-slate-950/90 p-4 font-mono text-[12px] leading-relaxed text-slate-200 ring-1 ring-white/10 outline-none focus:ring-2 focus:ring-amber-400/60"
            />
            {error && <p className="mt-1.5 text-xs font-semibold text-rose-600 dark:text-rose-300">{error}</p>}
          </div>
        ) : (
          <ActionPreview tool={action.tool} args={shown} />
        )}
      </div>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Segmented<DraftType>
          ariaLabel={`Decision for ${humanize(action.tool)}`}
          value={draft.type}
          onChange={(type) => onChange({ ...draft, type })}
          options={[
            { value: "approve", label: "Approve", icon: CircleCheckBig, gradient: "from-emerald-500 to-teal-500" },
            { value: "edit", label: "Edit", icon: PencilLine, gradient: "from-amber-400 to-orange-500" },
            { value: "reject", label: "Reject", icon: Ban, gradient: "from-rose-500 to-red-500" },
          ]}
        />
        {!draft.type && <p className="text-xs text-ink-3">No default: choose one to continue.</p>}
      </div>

      <AnimatePresence>
        {draft.type === "reject" && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <input
              className={`${inputClass} mt-3`}
              placeholder="Reason for the agent (optional)"
              value={draft.message}
              onChange={(e) => onChange({ ...draft, message: e.target.value })}
            />
          </motion.div>
        )}
        {roleBlocked && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-3">
            <Callout tone="amber" icon={Crown}>
              You are signed in as an AP executive. This is above the approval limit, so the server will refuse it.
              Switch the role to <b>Finance manager</b> in the sidebar to approve.
            </Callout>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function ActionPreview({ tool, args }: { tool: string; args: Record<string, unknown> }) {
  if (tool === "draft_supplier_email" && typeof args.body === "string") {
    return (
      <div className="overflow-hidden rounded-2xl bg-surface-2 ring-1 ring-line ring-inset">
        <div className="space-y-1 border-b border-line px-4 py-3 text-[13px]">
          <p>
            <span className="inline-block w-16 text-ink-3">To</span>
            <span className="font-medium text-ink">{String(args.to_address ?? "—")}</span>
          </p>
          <p>
            <span className="inline-block w-16 text-ink-3">Subject</span>
            <span className="font-semibold text-ink">{String(args.subject ?? "—")}</span>
          </p>
        </div>
        <p className="max-h-72 overflow-y-auto px-4 py-3 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-2">{args.body}</p>
      </div>
    );
  }
  if (tool === "propose_fix") {
    const { action, pay_amount, debit_note_amount, explanation, finding, ...rest } = args;
    return (
      <div className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <Figure label="Resolution" value={humanize(String(action ?? "—"))} />
          <Figure label="Release for payment" value={rupees(pay_amount as number)} accent="text-emerald-600 dark:text-emerald-300" />
          <Figure label="Debit note" value={rupees(debit_note_amount as number)} accent="text-rose-600 dark:text-rose-300" />
        </div>
        {typeof explanation === "string" && <p className="rounded-xl bg-sunk px-4 py-3 text-[13px] leading-relaxed text-ink-2 ring-1 ring-line ring-inset">{explanation}</p>}
        {typeof finding === "string" && (
          <details className="rounded-xl bg-sunk px-4 py-3 text-[13px] ring-1 ring-line ring-inset">
            <summary className="cursor-pointer font-semibold text-ink-2">The finding behind it</summary>
            <p className="mt-2 leading-relaxed text-ink-3">{finding}</p>
          </details>
        )}
        {Object.keys(rest).length > 0 && <JsonView value={rest} />}
      </div>
    );
  }
  return <JsonView value={args} />;
}

function Figure({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl bg-sunk px-3.5 py-3 ring-1 ring-line ring-inset">
      <p className="text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{label}</p>
      <p className={`mt-1 text-lg font-semibold tracking-tight tabular ${accent ?? "text-ink"}`}>{value}</p>
    </div>
  );
}
