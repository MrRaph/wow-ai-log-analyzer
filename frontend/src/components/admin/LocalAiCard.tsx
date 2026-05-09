"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Square, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button, Card, Input, Label } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type {
  LocalAiModelConfig,
  LocalAiModelFile,
  LocalAiStatus,
} from "@/types/api";

const DEFAULT_FORM: LocalAiModelConfig = {
  hf_repo: "",
  hf_file: "",
  alias: "",
  ctx_size: 16384,
  enable_thinking: true,
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}

export function LocalAiCard() {
  const t = useTranslations();
  const qc = useQueryClient();
  const [form, setForm] = useState<LocalAiModelConfig>(DEFAULT_FORM);
  const [dirty, setDirty] = useState(false);

  const statusQ = useQuery({
    queryKey: ["admin-local-ai-status"],
    queryFn: () => apiFetch<LocalAiStatus>("/api/v1/admin/local-ai/status"),
    // Poll faster while a download is active or the child is still
    // booting; otherwise once every 15 s is fine.
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return 5000;
      if (d.download && !d.download.finished_at) return 1500;
      if (d.desired_running && !d.child_healthy) return 3000;
      return 15000;
    },
  });

  const modelsQ = useQuery({
    queryKey: ["admin-local-ai-models"],
    queryFn: () =>
      apiFetch<LocalAiModelFile[]>("/api/v1/admin/local-ai/models"),
    refetchInterval: 10000,
    enabled: !!statusQ.data?.reachable,
  });

  // Keep the form in sync with the supervisor's current config until the
  // user starts editing — then we stop overwriting their input.
  useEffect(() => {
    if (!dirty && statusQ.data?.config) {
      setForm(statusQ.data.config);
    }
  }, [statusQ.data?.config, dirty]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiFetch<LocalAiStatus>("/api/v1/admin/local-ai/config", {
        method: "PATCH",
        body: { config: form },
      }),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["admin-local-ai-status"] });
      qc.invalidateQueries({ queryKey: ["admin-local-ai-models"] });
    },
    onError: (e) => {
      window.alert(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  const startMut = useMutation({
    mutationFn: () =>
      apiFetch<LocalAiStatus>("/api/v1/admin/local-ai/start", {
        method: "POST",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-local-ai-status"] }),
  });

  const stopMut = useMutation({
    mutationFn: () =>
      apiFetch<LocalAiStatus>("/api/v1/admin/local-ai/stop", {
        method: "POST",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-local-ai-status"] }),
  });

  const deleteMut = useMutation({
    mutationFn: (filename: string) =>
      apiFetch(`/api/v1/admin/local-ai/models/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-local-ai-models"] }),
    onError: (e) => {
      window.alert(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  const status = statusQ.data;
  // Hide while we don't yet know whether the supervisor is up — avoids
  // a half-second of "Container nicht erreichbar" flash on every load.
  if (statusQ.isLoading) return null;

  if (!status?.reachable) {
    return (
      <Card id="local-ai-card">
        <h2 className="text-lg font-semibold">{t("admin.localAi.title")}</h2>
        <p className="mt-2 text-sm text-zinc-400">
          {t("admin.localAi.unreachable")}
        </p>
      </Card>
    );
  }

  const dl = status.download;
  const dlActive = !!dl && !dl.finished_at && !dl.error;

  return (
    <Card id="local-ai-card">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("admin.localAi.title")}</h2>
        <span
          className={
            status.child_healthy
              ? "text-sm text-emerald-300"
              : status.desired_running
                ? "text-sm text-yellow-300"
                : "text-sm text-zinc-400"
          }
        >
          {status.child_healthy
            ? t("admin.localAi.statusReady")
            : status.desired_running
              ? t("admin.localAi.statusStarting")
              : t("admin.localAi.statusStopped")}
          {status.current_model_filename
            ? ` · ${status.current_model_filename}`
            : ""}
        </span>
      </div>
      <p className="mt-2 text-sm text-zinc-400">
        {t("admin.localAi.help")}
      </p>

      {/* Live download progress */}
      {dl && (
        <div className="mt-4 rounded-md border border-bg-3 bg-bg-2/40 p-3">
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="font-medium text-zinc-100">
              {t("admin.localAi.downloading")}: {dl.filename}
            </span>
            <span className="text-xs text-zinc-400">
              {formatBytes(dl.bytes_done)}
              {dl.bytes_total ? ` / ${formatBytes(dl.bytes_total)}` : ""}
              {dl.percent !== null ? ` · ${dl.percent.toFixed(1)}%` : ""}
            </span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded bg-bg-3">
            <div
              className={`h-full ${
                dl.error ? "bg-red-500" : dlActive ? "bg-amber-500" : "bg-emerald-500"
              } transition-all`}
              style={{ width: `${Math.max(0, Math.min(100, dl.percent ?? 0))}%` }}
            />
          </div>
          {dl.error && (
            <p className="mt-2 text-xs text-red-300">{dl.error}</p>
          )}
        </div>
      )}

      {/* Config form */}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="md:col-span-2">
          <Label>{t("admin.localAi.hfRepo")}</Label>
          <Input
            value={form.hf_repo}
            onChange={(e) => {
              setDirty(true);
              setForm({ ...form, hf_repo: e.target.value });
            }}
            placeholder="HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive"
          />
        </div>
        <div>
          <Label>{t("admin.localAi.hfFile")}</Label>
          <Input
            value={form.hf_file}
            onChange={(e) => {
              setDirty(true);
              setForm({ ...form, hf_file: e.target.value });
            }}
            placeholder="*.Q4_K_M.gguf"
          />
        </div>
        <div>
          <Label>{t("admin.localAi.alias")}</Label>
          <Input
            value={form.alias}
            onChange={(e) => {
              setDirty(true);
              setForm({ ...form, alias: e.target.value });
            }}
            placeholder="qwen3.6-35b-a3b-q4_k_m"
          />
        </div>
        <div>
          <Label>{t("admin.localAi.ctxSize")}</Label>
          <Input
            type="number"
            min={512}
            max={1000000}
            step={1024}
            value={form.ctx_size}
            onChange={(e) => {
              setDirty(true);
              setForm({ ...form, ctx_size: Number(e.target.value) || 0 });
            }}
          />
        </div>
        <div className="flex items-center gap-3">
          <input
            id="enableThinking"
            type="checkbox"
            checked={form.enable_thinking}
            onChange={(e) => {
              setDirty(true);
              setForm({ ...form, enable_thinking: e.target.checked });
            }}
            className="h-4 w-4 accent-amber-500"
          />
          <label htmlFor="enableThinking" className="text-sm">
            {t("admin.localAi.enableThinking")}
          </label>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending || !form.hf_repo || !form.hf_file || !form.alias}
        >
          {saveMut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            t("admin.localAi.applyConfig")
          )}
        </Button>
        {status.desired_running ? (
          <Button
            variant="secondary"
            onClick={() => stopMut.mutate()}
            disabled={stopMut.isPending}
            title={t("admin.localAi.stopHint")}
          >
            <Square className="mr-1 h-4 w-4" aria-hidden="true" />
            {t("admin.localAi.stop")}
          </Button>
        ) : (
          <Button
            variant="secondary"
            onClick={() => startMut.mutate()}
            disabled={startMut.isPending}
            title={t("admin.localAi.startHint")}
          >
            <Play className="mr-1 h-4 w-4" aria-hidden="true" />
            {t("admin.localAi.start")}
          </Button>
        )}
        {dirty && (
          <span className="text-xs text-amber-300">
            {t("admin.localAi.unsaved")}
          </span>
        )}
      </div>

      {status.last_error && (
        <p className="mt-3 rounded bg-red-500/10 p-2 text-sm text-red-300">
          {status.last_error}
        </p>
      )}

      {/* Cached model files */}
      <div className="mt-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">
          {t("admin.localAi.cachedModels")}
        </h3>
        <div className="mt-2 space-y-1">
          {(modelsQ.data ?? []).map((m) => (
            <div
              key={m.filename}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-bg-3 bg-bg-2/40 px-3 py-2 text-sm"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-zinc-100">
                  {m.filename}
                  {m.is_loaded && (
                    <span className="ml-2 rounded bg-emerald-500/15 px-1.5 py-0.5 text-xs text-emerald-300">
                      {t("admin.localAi.loaded")}
                    </span>
                  )}
                </div>
                <div className="text-xs text-zinc-500">
                  {formatBytes(m.size_bytes)}
                </div>
              </div>
              <Button
                size="sm"
                variant="danger"
                disabled={
                  m.is_loaded ||
                  (deleteMut.isPending && deleteMut.variables === m.filename)
                }
                title={
                  m.is_loaded
                    ? t("admin.localAi.deleteLoadedHint")
                    : t("admin.localAi.delete")
                }
                aria-label={t("admin.localAi.delete")}
                onClick={() => {
                  if (window.confirm(t("admin.localAi.deleteConfirm", { filename: m.filename }))) {
                    deleteMut.mutate(m.filename);
                  }
                }}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ))}
          {modelsQ.data && modelsQ.data.length === 0 && (
            <p className="text-sm text-zinc-500">
              {t("admin.localAi.noCachedModels")}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
