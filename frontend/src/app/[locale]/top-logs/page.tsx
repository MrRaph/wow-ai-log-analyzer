"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { use, useEffect, useMemo, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { ClassBadge } from "@/components/ClassBadge";
import { Button, Card, Label, Select } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { formatNumber, formatDuration } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { GameClass, GameSpec, TopLog, UserOut } from "@/types/api";

export default function TopLogsPage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  return <AuthGuard locale={locale}>{(user) => <TopLogsView locale={locale} user={user} />}</AuthGuard>;
}

function TopLogsView({ locale, user }: { locale: Locale; user: UserOut }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const classesQ = useQuery({
    queryKey: ["classes"],
    queryFn: () => apiFetch<GameClass[]>("/api/v1/classes"),
  });
  const [classSlug, setClassSlug] = useState<string>("");
  const [specSlug, setSpecSlug] = useState<string>("");
  const [encounterId, setEncounterId] = useState<string>("");
  const [wclFlavor, setWclFlavor] = useState<"retail" | "fresh">("retail");

  useEffect(() => {
    if (!classSlug && classesQ.data?.length) {
      setClassSlug(classesQ.data[0]!.slug);
      setSpecSlug(classesQ.data[0]!.specs[0]?.slug ?? "");
    }
  }, [classesQ.data, classSlug]);

  const cls = classesQ.data?.find((c) => c.slug === classSlug);
  const spec: GameSpec | undefined = cls?.specs.find((s) => s.slug === specSlug);
  const metric = spec?.role === "healer" ? "hps" : "dps";

  const topLogsQ = useQuery({
    queryKey: ["top-logs", specSlug, encounterId, metric, wclFlavor],
    queryFn: () =>
      apiFetch<TopLog[]>(
        `/api/v1/top-logs?spec_slug=${specSlug}` +
          (encounterId ? `&encounter_id=${encounterId}` : "") +
          `&metric=${metric}&wcl_flavor=${wclFlavor}`,
      ),
    enabled: !!specSlug,
  });

  const refreshMut = useMutation({
    mutationFn: () => {
      if (!specSlug || !encounterId) throw new Error("encounter_id required");
      return apiFetch(
        `/api/v1/top-logs/refresh?spec_slug=${specSlug}&encounter_id=${encounterId}&metric=${metric}&wcl_flavor=${wclFlavor}`,
        { method: "POST" },
      );
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["top-logs", specSlug, encounterId, metric, wclFlavor] }),
  });

  const grouped = useMemo(() => {
    const map = new Map<number, TopLog[]>();
    for (const row of topLogsQ.data ?? []) {
      const list = map.get(row.encounter_id) ?? [];
      list.push(row);
      map.set(row.encounter_id, list);
    }
    return [...map.entries()];
  }, [topLogsQ.data]);

  return (
    <div className="container-page space-y-4">
      <header>
        <h1 className="font-display text-3xl font-semibold">{t("topLogs.title")}</h1>
      </header>
      <Card>
        <div className="grid gap-4 md:grid-cols-5">
          <div>
            <Label>{t("topLogs.selectClass")}</Label>
            <Select
              value={classSlug}
              onChange={(e) => {
                setClassSlug(e.target.value);
                const c = classesQ.data?.find((cc) => cc.slug === e.target.value);
                setSpecSlug(c?.specs[0]?.slug ?? "");
              }}
            >
              {classesQ.data?.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {locale === "de" ? c.name_de : c.name_en}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>{t("topLogs.selectSpec")}</Label>
            <Select value={specSlug} onChange={(e) => setSpecSlug(e.target.value)}>
              {cls?.specs.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {locale === "de" ? s.name_de : s.name_en}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>{locale === "de" ? "Boss (optional)" : "Boss (optional)"}</Label>
            <Select value={encounterId} onChange={(e) => setEncounterId(e.target.value)}>
              <option value="">{locale === "de" ? "Alle Bosse" : "All bosses"}</option>
              {(() => {
                const seen = new Map<number, string>();
                for (const r of topLogsQ.data ?? []) {
                  if (!seen.has(r.encounter_id)) {
                    seen.set(
                      r.encounter_id,
                      r.encounter_name_localized || r.encounter_name || `#${r.encounter_id}`,
                    );
                  }
                }
                return [...seen.entries()]
                  .sort((a, b) => a[1].localeCompare(b[1], locale))
                  .map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ));
              })()}
            </Select>
          </div>
          <div>
            <Label>{t("topLogs.sourceLabel")}</Label>
            <Select value={wclFlavor} onChange={(e) => setWclFlavor(e.target.value as "retail" | "fresh")}>
              <option value="retail">{t("topLogs.sourceRetail")}</option>
              <option value="fresh">{t("topLogs.sourceFresh")}</option>
            </Select>
          </div>
          <div className="flex items-end">
            <span className="text-xs uppercase tracking-wide text-zinc-400">
              {t("topLogs.selectMetric")}: <span className="ml-1 text-accent">{metric.toUpperCase()}</span>
            </span>
          </div>
        </div>
        {user.role === "admin" && encounterId && (
          <div className="mt-3 flex justify-end">
            <Button size="sm" variant="secondary" onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}>
              {refreshMut.isPending ? t("common.loading") : t("topLogs.refresh")}
            </Button>
          </div>
        )}
      </Card>

      {topLogsQ.isLoading && <p className="text-zinc-400">{t("common.loading")}</p>}
      {!topLogsQ.isLoading && grouped.length === 0 && (
        <Card>
          <p className="text-sm text-zinc-300">{t("topLogs.noResults")}</p>
        </Card>
      )}

      {grouped.map(([id, rows]) => (
        <Card key={id} className="!p-0 overflow-hidden">
          <div className="flex items-center justify-between border-b border-bg-3 bg-bg-2 px-4 py-3">
            <h3 className="text-sm font-semibold">
              {rows[0]?.encounter_name_localized || rows[0]?.encounter_name || `Encounter ${id}`} ·{" "}
              {metric.toUpperCase()}
            </h3>
            {cls && spec && (
              <span className="text-xs"><ClassBadge cls={cls} spec={spec} locale={locale} /></span>
            )}
          </div>
          {/* Desktop: classic table */}
          <table className="hidden w-full text-sm md:table">
            <thead className="text-xs uppercase tracking-wide text-zinc-400">
              <tr>
                <th className="px-3 py-2 text-left">{t("topLogs.rank")}</th>
                <th className="px-3 py-2 text-left">{t("topLogs.character")}</th>
                <th className="px-3 py-2 text-right">{t("topLogs.amount")}</th>
                <th className="px-3 py-2 text-right">{t("topLogs.ilvl")}</th>
                <th className="px-3 py-2 text-right">{t("topLogs.duration")}</th>
                <th className="px-3 py-2 text-right">WCL</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-bg-3">
                  <td className="px-3 py-2 text-zinc-400">{r.rank}</td>
                  <td className="px-3 py-2">
                    <span className="text-zinc-100">{r.character_name}</span>
                    <span className="ml-2 text-xs text-zinc-500">
                      {r.server} · {r.region.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatNumber(r.amount, locale)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {r.item_level ? r.item_level.toFixed(0) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatDuration(r.duration_ms)}</td>
                  <td className="px-3 py-2 text-right">
                    <a
                      href={`${
                        r.wcl_flavor === "fresh"
                          ? "https://fresh.warcraftlogs.com"
                          : r.wcl_flavor === "classic"
                            ? "https://classic.warcraftlogs.com"
                            : "https://www.warcraftlogs.com"
                      }/reports/${r.wcl_report_code}#fight=${r.wcl_fight_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("topLogs.openOnWcl")}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Mobile: stacked card layout */}
          <ul className="divide-y divide-bg-3 md:hidden">
            {rows.map((r) => (
              <li key={r.id} className="space-y-1 px-4 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="shrink-0 text-xs font-semibold text-zinc-400">
                      #{r.rank}
                    </span>
                    <span className="truncate text-sm text-zinc-100">{r.character_name}</span>
                  </div>
                  <span className="shrink-0 text-sm font-semibold tabular-nums text-accent">
                    {formatNumber(r.amount, locale)}
                  </span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-zinc-500">
                  <span className="truncate">
                    {r.server} · {r.region.toUpperCase()}
                  </span>
                  <span className="tabular-nums">
                    {t("topLogs.ilvl")} {r.item_level ? r.item_level.toFixed(0) : "—"} ·{" "}
                    {formatDuration(r.duration_ms)}
                  </span>
                  <a
                    href={`${
                      r.wcl_flavor === "fresh"
                        ? "https://fresh.warcraftlogs.com"
                        : r.wcl_flavor === "classic"
                          ? "https://classic.warcraftlogs.com"
                          : "https://www.warcraftlogs.com"
                    }/reports/${r.wcl_report_code}#fight=${r.wcl_fight_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent"
                  >
                    {t("topLogs.openOnWcl")}
                  </a>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
