"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { Button, Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { WowDataImport, WowDataStatus } from "@/types/api";

export function WowDataCard({ locale }: { locale: Locale }) {
  const t = useTranslations();
  const qc = useQueryClient();

  const statusQ = useQuery({
    queryKey: ["wow-data-status"],
    queryFn: () => apiFetch<WowDataStatus>("/api/v1/admin/wow-data"),
    // Poll while an import is in progress so the UI updates live.
    refetchInterval: (q) =>
      q.state.data?.last_import?.status === "in_progress" ? 4000 : false,
  });

  const refreshMut = useMutation({
    mutationFn: () =>
      apiFetch<WowDataImport>("/api/v1/admin/wow-data/refresh", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wow-data-status"] }),
  });

  const status = statusQ.data;
  const lastImport = status?.last_import;
  const newerAvailable =
    !!status?.latest_known_build &&
    !!lastImport &&
    lastImport.build !== status.latest_known_build &&
    lastImport.status === "success";

  const statusLabel = lastImport
    ? lastImport.status === "in_progress"
      ? t("admin.wowDataStatusInProgress")
      : lastImport.status === "success"
        ? t("admin.wowDataStatusSuccess")
        : t("admin.wowDataStatusFailed")
    : t("admin.wowDataStatusNone");

  const statusClass = lastImport
    ? lastImport.status === "in_progress"
      ? "text-yellow-300"
      : lastImport.status === "success"
        ? "text-emerald-300"
        : "text-red-300"
    : "text-zinc-400";

  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("admin.wowData")}</h2>
        <span className={`text-sm font-medium ${statusClass}`}>{statusLabel}</span>
      </div>
      <p className="mt-2 text-sm text-zinc-400">{t("admin.wowDataHelp")}</p>

      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase tracking-wide text-zinc-500">
            {t("admin.wowDataLastImport")}
          </dt>
          <dd className="text-zinc-100">
            {lastImport
              ? `${lastImport.build} · ${formatDateTime(lastImport.started_at, locale)}`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-zinc-500">
            {t("admin.wowDataLatestBuild")}
          </dt>
          <dd className="text-zinc-100">{status?.latest_known_build ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-zinc-500">
            {t("admin.wowDataRowsImported")}
          </dt>
          <dd className="text-zinc-100">
            {lastImport ? formatNumber(lastImport.rows_imported, locale) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-zinc-500">Counts</dt>
          <dd className="text-xs text-zinc-300">
            {status?.counts && Object.keys(status.counts).length > 0
              ? Object.entries(status.counts)
                  .map(
                    ([kind, perLocale]) =>
                      `${kind}: ${Object.entries(perLocale)
                        .map(([loc, n]) => `${loc}=${formatNumber(n, locale)}`)
                        .join(" / ")}`,
                  )
                  .join(" · ")
              : "—"}
          </dd>
        </div>
      </dl>

      {newerAvailable && (
        <p className="mt-3 rounded bg-yellow-500/10 p-2 text-sm text-yellow-300">
          {t("admin.wowDataNewer")} {status?.latest_known_build}
        </p>
      )}
      {refreshMut.isError && (
        <p className="mt-3 text-sm text-red-400">
          {refreshMut.error instanceof ApiClientError
            ? refreshMut.error.message
            : t("errors.generic")}
        </p>
      )}

      <div className="mt-4">
        <Button
          onClick={() => refreshMut.mutate()}
          disabled={
            refreshMut.isPending || lastImport?.status === "in_progress"
          }
        >
          {lastImport?.status === "in_progress"
            ? t("admin.wowDataStatusInProgress")
            : refreshMut.isPending
              ? t("common.loading")
              : t("admin.wowDataRefresh")}
        </Button>
      </div>
    </Card>
  );
}
