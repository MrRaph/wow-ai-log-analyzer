"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Card, FieldError, Input, Label, Select } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { TopLogsEncounterRow } from "@/types/api";

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
