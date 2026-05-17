"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Hammer, Loader2, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { Button, Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type { SimcStatus } from "@/types/api";

interface RebuildStatus {
  id?: string;
  status: "idle" | "queued" | "running" | "succeeded" | "failed" | "cancelled";
  started_at?: number | null;
  finished_at?: number | null;
  error?: string | null;
  used_dbcache?: boolean;
  log_tail?: string;
}

export function SimcCard() {
  const t = useTranslations();
  const qc = useQueryClient();

  const statusQ = useQuery({
    queryKey: ["admin-simc-status"],
    queryFn: () => apiFetch<SimcStatus>("/api/v1/admin/simc/status"),
    // Refetch every 30s while the container is in a transitional state, else
    // a lazy 2 min — admins don't need millisecond freshness here.
    refetchInterval: (q) => {
      const c = q.state.data?.container;
      if (c && (c.status === "restarting" || c.health === "starting")) return 5000;
      return 120000;
    },
  });

  const updateMut = useMutation({
    mutationFn: () =>
      apiFetch<SimcStatus>("/api/v1/admin/simc/update", { method: "POST" }),
    onSuccess: (s) => {
      qc.setQueryData(["admin-simc-status"], s);
      qc.invalidateQueries({ queryKey: ["admin-system"] });
    },
  });

  // --- "Rebuild from source" with optional DBCache.bin upload ----------------
  // While the upstream daily Docker image catches the common case, the
  // ~1-3 day lag between a WoW hotfix and the next public simc release
  // matters when the user has a /simc paste from a freshly-patched
  // build. The rebuild path bakes a fresh simc binary in-place from
  // CDN data + (optionally) the user's DBCache.bin.
  const rebuildFileRef = useRef<HTMLInputElement | null>(null);
  const [rebuildFile, setRebuildFile] = useState<File | null>(null);

  const rebuildStatusQ = useQuery({
    queryKey: ["admin-simc-rebuild-status"],
    queryFn: () =>
      apiFetch<RebuildStatus>("/api/v1/admin/simc/rebuild-status"),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 3000 : false;
    },
  });

  const rebuildMut = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      if (rebuildFile) fd.append("dbcache", rebuildFile);
      // apiFetch wraps fetch; for multipart we hand it the FormData and
      // let the browser set the boundary.
      return apiFetch<RebuildStatus>("/api/v1/admin/simc/rebuild", {
        method: "POST",
        body: fd,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-simc-rebuild-status"] });
      setRebuildFile(null);
      if (rebuildFileRef.current) rebuildFileRef.current.value = "";
    },
  });

  const data = statusQ.data;
  const banner = data?.build_banner || "";
  const reachable = data?.reachable ?? false;
  const errMsg =
    updateMut.error instanceof ApiClientError
      ? updateMut.error.message
      : updateMut.error
        ? t("errors.generic")
        : null;

  return (
    <Card>
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("adminSimc.title")}</h2>
        <span
          className={`text-xs ${reachable ? "text-emerald-300" : "text-zinc-400"}`}
        >
          {reachable ? t("adminSimc.ready") : t("adminSimc.unreachable")}
        </span>
      </header>
      <p className="mb-3 text-xs text-zinc-500">{t("adminSimc.hint")}</p>

      <dl className="mb-4 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase text-zinc-500">
            {t("adminSimc.baseUrl")}
          </dt>
          <dd className="font-mono text-xs text-zinc-200">
            {data?.base_url || "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-zinc-500">
            {t("adminSimc.build")}
          </dt>
          <dd className="font-mono text-xs text-zinc-200 break-all">
            {banner || "—"}
          </dd>
        </div>
        {data?.container && (
          <>
            <div>
              <dt className="text-xs uppercase text-zinc-500">
                {t("adminSimc.containerImage")}
              </dt>
              <dd className="font-mono text-xs text-zinc-200 break-all">
                {data.container.image}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-zinc-500">
                {t("adminSimc.containerStatus")}
              </dt>
              <dd className="text-xs text-zinc-200">
                {data.container.status}
                {data.container.health ? ` (${data.container.health})` : ""}
              </dd>
            </div>
          </>
        )}
      </dl>

      <Button
        type="button"
        onClick={() => updateMut.mutate()}
        disabled={updateMut.isPending}
        className="inline-flex items-center gap-2"
      >
        {updateMut.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        {updateMut.isPending
          ? t("adminSimc.updating")
          : t("adminSimc.updateNow")}
      </Button>
      {errMsg && (
        <p className="mt-2 text-xs text-red-300">{errMsg}</p>
      )}

      <hr className="my-4 border-bg-3" />

      <div>
        <h3 className="text-sm font-semibold text-zinc-100">
          {t("adminSimc.rebuildTitle")}
        </h3>
        <p className="mt-1 text-xs text-zinc-500">{t("adminSimc.rebuildHint")}</p>

        <label className="mt-3 flex items-center gap-2 text-xs text-zinc-300">
          <input
            ref={rebuildFileRef}
            type="file"
            accept=".bin,application/octet-stream"
            onChange={(e) => setRebuildFile(e.target.files?.[0] ?? null)}
            className="block w-full max-w-md text-xs text-zinc-300 file:mr-3 file:rounded file:border-0 file:bg-bg-3 file:px-3 file:py-1.5 file:text-xs file:text-zinc-100 hover:file:bg-bg-2"
          />
        </label>
        <p className="mt-1 text-xs text-zinc-500">{t("adminSimc.dbcacheHint")}</p>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button
            type="button"
            onClick={() => rebuildMut.mutate()}
            disabled={
              rebuildMut.isPending ||
              rebuildStatusQ.data?.status === "queued" ||
              rebuildStatusQ.data?.status === "running"
            }
            className="inline-flex items-center gap-2"
          >
            {rebuildMut.isPending ||
            rebuildStatusQ.data?.status === "queued" ||
            rebuildStatusQ.data?.status === "running" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Hammer className="h-4 w-4" />
            )}
            {rebuildStatusQ.data?.status === "running"
              ? t("adminSimc.rebuildRunning")
              : t("adminSimc.rebuildNow")}
          </Button>
          {rebuildFile && (
            <span className="text-xs text-zinc-400">
              <Upload className="mr-1 inline h-3 w-3" />
              {rebuildFile.name} (
              {(rebuildFile.size / 1024).toFixed(0)} KB)
            </span>
          )}
        </div>

        {rebuildStatusQ.data && rebuildStatusQ.data.status !== "idle" && (
          <div className="mt-3 rounded-md border border-bg-3 bg-bg-2/50 p-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-zinc-200">
                {t(`adminSimc.rebuildStatus.${rebuildStatusQ.data.status}`)}
              </span>
              {rebuildStatusQ.data.used_dbcache && (
                <span className="text-emerald-300">
                  {t("adminSimc.dbcacheLayered")}
                </span>
              )}
            </div>
            {rebuildStatusQ.data.error && (
              <p className="mt-1 text-xs text-red-300">
                {rebuildStatusQ.data.error}
              </p>
            )}
            {rebuildStatusQ.data.log_tail && (
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-[10px] leading-tight text-zinc-400">
                {rebuildStatusQ.data.log_tail}
              </pre>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
