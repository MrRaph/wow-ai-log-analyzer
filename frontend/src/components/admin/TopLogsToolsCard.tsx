"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, FieldError, Input, Label, Select } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type {
  TopLogsCurrentTierResponse,
  TopLogsEncounterRow,
  TopLogsSeedJob,
} from "@/types/api";

export function TopLogsToolsCard({ locale }: { locale: Locale }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const [encounterId, setEncounterId] = useState("");
  const [isRaid, setIsRaid] = useState(true);
  const [metricFilter, setMetricFilter] = useState<"" | "dps" | "hps">("");
  const [flash, setFlash] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const encountersQ = useQuery({
    queryKey: ["admin-top-logs-encounters"],
    queryFn: () =>
      apiFetch<TopLogsEncounterRow[]>("/api/v1/admin/top-logs/encounters"),
  });

  // Live-progress source for the seed-jobs section. Polls every 2 s while
  // any job is still running; stops automatically when the list is empty.
  const seedJobsQ = useQuery({
    queryKey: ["admin-top-logs-seed-jobs"],
    queryFn: () =>
      apiFetch<TopLogsSeedJob[]>("/api/v1/admin/top-logs/seed-jobs?active_only=true"),
    refetchInterval: (q) => ((q.state.data ?? []).length > 0 ? 2000 : false),
  });

  // Preview what seed-current-tier would queue. Refetches when the user
  // expands the section so the list stays in sync with the WCL state.
  const tierPreviewQ = useQuery({
    queryKey: ["admin-top-logs-current-tier-preview"],
    queryFn: () =>
      apiFetch<{
        expansion_id: number | null;
        expansion_name: string | null;
        zones?: Array<{
          zone_id: number;
          zone_name: string;
          encounters: Array<{ encounter_id: number; encounter_name: string }>;
        }>;
        total_encounters?: number;
      }>("/api/v1/admin/top-logs/current-tier-preview"),
    // 10 min — zones list barely changes.
    staleTime: 10 * 60 * 1000,
  });

  const seedTierMut = useMutation({
    mutationFn: () =>
      apiFetch<TopLogsCurrentTierResponse>(
        "/api/v1/admin/top-logs/seed-current-tier",
        { method: "POST" },
      ),
    onSuccess: (data) => {
      const skipped = data.skipped_already_running;
      setFlash(
        skipped > 0
          ? `${t("admin.topLogsTierQueued", { queued: data.queued, skipped })}`
          : `${t("admin.topLogsTierQueuedSimple", { queued: data.queued })}`,
      );
      setErr(null);
      qc.invalidateQueries({ queryKey: ["admin-top-logs-seed-jobs"] });
      qc.invalidateQueries({ queryKey: ["admin-top-logs-encounters"] });
    },
    onError: (e) =>
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic")),
  });

  const seedMut = useMutation({
    mutationFn: ({
      id,
      raid,
      metric,
    }: {
      id: number;
      raid: boolean;
      metric?: "dps" | "hps";
    }) =>
      apiFetch<{ queued: boolean; spec_count: number; metric: string | null }>(
        "/api/v1/admin/top-logs/seed-encounter",
        {
          method: "POST",
          body: {
            encounter_id: id,
            is_raid: raid,
            ...(metric ? { metric } : {}),
          },
        },
      ),
    onSuccess: (data) => {
      setFlash(
        `${t("admin.topLogsSeedQueued")} (${data.spec_count} spec${data.spec_count === 1 ? "" : "s"}${
          data.metric ? `, ${data.metric.toUpperCase()}` : ""
        })`,
      );
      setErr(null);
      setEncounterId("");
      qc.invalidateQueries({ queryKey: ["admin-top-logs-encounters"] });
      qc.invalidateQueries({ queryKey: ["admin-top-logs-seed-jobs"] });
    },
    onError: (e) =>
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic")),
  });

  const submitNew = (e: React.FormEvent) => {
    e.preventDefault();
    setFlash(null);
    setErr(null);
    const id = parseInt(encounterId.trim(), 10);
    if (!Number.isFinite(id) || id <= 0) {
      setErr("Encounter ID must be a positive integer");
      return;
    }
    seedMut.mutate({
      id,
      raid: isRaid,
      metric: metricFilter || undefined,
    });
  };

  return (
    <Card>
      <h2 className="text-lg font-semibold">{t("admin.topLogsTools")}</h2>
      <p className="mt-1 text-sm text-zinc-400">{t("admin.topLogsToolsHelp")}</p>

      <form
        onSubmit={submitNew}
        className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto_auto] md:items-end"
      >
        <div>
          <Label>{t("admin.topLogsAddEncounter")}</Label>
          <Input
            inputMode="numeric"
            placeholder="e.g. 3176"
            value={encounterId}
            onChange={(e) => setEncounterId(e.target.value)}
          />
        </div>
        <div>
          <Label>{t("admin.topLogsMetric")}</Label>
          <Select
            value={metricFilter}
            onChange={(e) => setMetricFilter(e.target.value as "" | "dps" | "hps")}
            className="!w-32"
          >
            <option value="">{t("admin.topLogsMetricAll")}</option>
            <option value="dps">DPS</option>
            <option value="hps">HPS</option>
          </Select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isRaid}
            onChange={(e) => setIsRaid(e.target.checked)}
            className="h-4 w-4 accent-amber-500"
          />
          {t("admin.topLogsIsRaid")}
        </label>
        <Button type="submit" disabled={seedMut.isPending}>
          {seedMut.isPending ? t("common.loading") : t("admin.topLogsSeed")}
        </Button>
      </form>
      <FieldError>{err}</FieldError>
      {flash && <p className="mt-2 text-sm text-emerald-300">{flash}</p>}

      {/* One-click: seed every encounter of the current retail raid tier.
          Backend hits the WCL zones API to discover what "current" means. */}
      <div className="mt-6 rounded-lg border border-bg-3 bg-bg-2/40 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">{t("admin.topLogsTierTitle")}</h3>
            <p className="mt-1 text-xs text-zinc-400">{t("admin.topLogsTierHint")}</p>
          </div>
          <Button
            onClick={() => {
              if (window.confirm(t("admin.topLogsTierConfirm"))) {
                seedTierMut.mutate();
              }
            }}
            disabled={seedTierMut.isPending}
            className="inline-flex items-center gap-2"
          >
            {seedTierMut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            )}
            {t("admin.topLogsTierButton")}
          </Button>
        </div>

        {tierPreviewQ.data && (tierPreviewQ.data.zones?.length ?? 0) > 0 && (
          <div className="mt-3 space-y-2 text-xs">
            <p className="text-zinc-400">
              {t("admin.topLogsTierPreviewTitle", {
                expansion:
                  tierPreviewQ.data.expansion_name ??
                  String(tierPreviewQ.data.expansion_id ?? "?"),
                count: tierPreviewQ.data.total_encounters ?? 0,
                zones: tierPreviewQ.data.zones?.length ?? 0,
              })}
            </p>
            {tierPreviewQ.data.zones?.map((zone) => (
              <div key={zone.zone_id} className="rounded bg-bg-2/60 p-2">
                <p className="font-medium text-zinc-200">{zone.zone_name}</p>
                <p className="mt-0.5 text-zinc-400">
                  {zone.encounters.map((e) => e.encounter_name).join(" · ")}
                </p>
              </div>
            ))}
          </div>
        )}
        {tierPreviewQ.data &&
          (tierPreviewQ.data.zones?.length ?? 0) === 0 && (
            <p className="mt-3 text-xs text-yellow-300">
              {t("admin.topLogsTierPreviewEmpty")}
            </p>
          )}
      </div>

      {/* Live progress: one row per non-terminal seed job. Polls every 2 s. */}
      {(seedJobsQ.data ?? []).length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            {t("admin.topLogsSeedProgressTitle")}
          </h3>
          <div className="space-y-2">
            {(seedJobsQ.data ?? []).map((job) => {
              const total = job.total_specs || 1;
              const pct = Math.min(100, (job.completed_specs / total) * 100);
              return (
                <div
                  key={job.id}
                  className="rounded-md border border-bg-3 bg-bg-2/40 p-3"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium text-zinc-100">
                      {job.encounter_name || `Encounter ${job.encounter_id}`}
                      {job.metric_filter && (
                        <span className="ml-2 rounded bg-bg-3 px-1.5 py-0.5 text-xs text-zinc-300">
                          {job.metric_filter.toUpperCase()}
                        </span>
                      )}
                    </span>
                    <span className="text-xs tabular-nums text-zinc-400">
                      {job.completed_specs}/{job.total_specs || "?"}{" "}
                      {t("admin.topLogsSeedProgressSpecs")}
                      {job.status === "queued" && (
                        <span className="ml-2 text-zinc-500">
                          · {t("admin.topLogsSeedQueuedLabel")}
                        </span>
                      )}
                      {job.current_spec_slug && (
                        <span className="ml-2 text-accent">
                          · {job.current_spec_slug}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-bg-3">
                    <div
                      className="h-full bg-accent transition-[width] duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-6">
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">
          {t("admin.topLogsCachedEncounters")}
        </h3>
        <div className="overflow-hidden rounded-md border border-bg-3">
          <table className="w-full text-sm">
            <thead className="bg-bg-2 text-xs uppercase tracking-wide text-zinc-400">
              <tr>
                <th className="px-3 py-2 text-left">ID</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-left">Metrics</th>
                <th className="px-3 py-2 text-right">{t("admin.topLogsRowsCached")}</th>
                <th className="px-3 py-2 text-left">{t("admin.wowDataLastImport")}</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {(encountersQ.data ?? []).map((row) => (
                <tr key={row.encounter_id} className="border-t border-bg-3">
                  <td className="px-3 py-2 tabular-nums text-zinc-300">{row.encounter_id}</td>
                  <td className="px-3 py-2 text-zinc-100">
                    {row.encounter_name_localized || row.encounter_name || "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-400">
                    {row.metrics.map((m) => m.toUpperCase()).join(" · ")}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatNumber(row.rows, locale)}
                  </td>
                  <td className="px-3 py-2 text-xs text-zinc-400">
                    {row.latest_recorded_at
                      ? formatDateTime(row.latest_recorded_at, locale)
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      {row.metrics.includes("dps") && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            seedMut.mutate({
                              id: row.encounter_id,
                              raid: isRaid,
                              metric: "dps",
                            })
                          }
                          disabled={seedMut.isPending}
                          title={t("admin.topLogsRefreshDps")}
                        >
                          DPS
                        </Button>
                      )}
                      {row.metrics.includes("hps") && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            seedMut.mutate({
                              id: row.encounter_id,
                              raid: isRaid,
                              metric: "hps",
                            })
                          }
                          disabled={seedMut.isPending}
                          title={t("admin.topLogsRefreshHps")}
                        >
                          HPS
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          seedMut.mutate({ id: row.encounter_id, raid: isRaid })
                        }
                        disabled={seedMut.isPending}
                        title={t("admin.topLogsRefreshOne")}
                      >
                        {t("admin.topLogsRefreshAll")}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {!encountersQ.isLoading && (encountersQ.data ?? []).length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-4 text-center text-sm text-zinc-500">
                    {t("topLogs.noResults")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  );
}
