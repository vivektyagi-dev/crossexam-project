import { getIdentity } from "./identity";
import type {
  Batch,
  BatchStatus,
  Decision,
  ExportResult,
  OutboxEmail,
  PackDetail,
  PackSummary,
  SheetPreview,
  Stats,
  UploadResult,
} from "./types";

// Same origin in every environment: Vite (dev) or app/ui/server.py (prod) forwards /api to FastAPI.
const BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function identityHeaders(): Record<string, string> {
  const { name, role } = getIdentity();
  return { "X-User": name || "anonymous", "X-Role": role };
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? JSON.stringify(d)).join("; ");
  }
  return fallback;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  for (const [k, v] of Object.entries(identityHeaders())) headers.set(k, v);
  const res = await fetch(BASE + path, { ...init, headers });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detailOf(body, res.statusText || `Request failed (${res.status})`));
  }
  return res;
}

const getJson = async <T>(path: string): Promise<T> => (await request(path)).json();

const postJson = async <T>(path: string, body: unknown): Promise<T> =>
  (await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })).json();

/** Uploads with XMLHttpRequest because fetch cannot report upload progress. */
function uploadBatch(form: FormData, onProgress: (fraction: number) => void): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/batches`);
    for (const [k, v] of Object.entries(identityHeaders())) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "Could not reach the server."));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* not JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as UploadResult);
      else reject(new ApiError(xhr.status, detailOf(body, xhr.statusText || "Upload failed")));
    };
    xhr.send(form);
  });
}

export const api = {
  batches: () => getJson<Batch[]>("/batches"),
  batch: (id: string) => getJson<BatchStatus>(`/batches/${id}`),
  uploadBatch,

  packs: (statuses: string[]) =>
    getJson<PackSummary[]>(`/packs?${new URLSearchParams(statuses.length ? { status: statuses.join(",") } : {})}`),
  pack: (id: string) => getJson<PackDetail>(`/packs/${id}`),
  decide: (id: string, decisions: Decision[]) => postJson<{ queued: boolean }>(`/packs/${id}/decisions`, { decisions }),
  manualDecision: (id: string, decision: "approve" | "reject", comment: string) =>
    postJson<{ ok: boolean }>(`/packs/${id}/manual-decision`, { decision, comment }),

  documentFile: async (id: string) => (await request(`/documents/${id}/file`)).blob(),
  documentTable: (id: string) => getJson<SheetPreview>(`/documents/${id}/table`),

  createExport: async (): Promise<ExportResult> => {
    const res = await request("/exports", { method: "POST" });
    const disposition = res.headers.get("Content-Disposition") ?? "";
    return {
      rows: Number(res.headers.get("X-Export-Rows") ?? 0),
      csv: await res.text(),
      filename: /filename=([^;]+)/.exec(disposition)?.[1]?.trim() ?? "erp-export.csv",
    };
  },
  outbox: () => getJson<OutboxEmail[]>("/outbox"),
  stats: (hours: number) => getJson<Stats>(`/stats?hours=${hours}`),
};
