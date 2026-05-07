"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { use, useState } from "react";

import { AnalysisCard } from "@/components/AnalysisCard";
import { AuthGuard } from "@/components/AuthGuard";
import { ClassBadge } from "@/components/ClassBadge";
import { Button, Card, FieldError, Input } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatNumber, formatDuration } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { Analysis, GameClass, Report, ReportFight, ReportPlayer, ReportSummary } from "@/types/api";

export default function AnalyzePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  return <AuthGuard locale={locale}>{() => <AnalyzeView locale={locale} />}</AuthGuard>;
}

function AnalyzeView({ locale }: { locale: Locale }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);

  const myReportsQ = useQuery({
    queryKey: ["my-reports"],
    queryFn: () => apiFetch<ReportSummary[]>("/api/v1/reports"),
  });

  const classesQ = useQuery({
    queryKey: ["classes"],
    queryFn: () => apiFetch<GameClass[]>("/api/v1/classes"),
  });

  const reportQ = useQuery({
    queryKey: ["report", activeReportId],
    queryFn: () => apiFetch<Report>(`/api/v1/reports/${activeReportId}`),
    enabled: !!activeReportId,
  });

  const importMut = useMutation({
    mutationFn: (raw: string) =>
      apiFetch<Report>("/api/v1/reports/import", {
        method: "POST",
        body: { wcl_url_or_code: raw },
      }),
    onSuccess: (report) => {
      setErr(null);
      setActiveReportId(report.id);
      qc.invalidateQueries({ queryKey: ["my-reports"] });
    },
    onError: (e) => setErr(e instanceof ApiClientError ? e.message : t("errors.generic")),
  });

  return (
    <div className="container-page space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold">{t("analyze.title")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">{t("analyze.subtitle")}</p>
      </header>

      <Card>
        <form
          className="flex flex-col gap-3 md:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!input.trim()) return;
            importMut.mutate(input.trim());
          }}
        >
          <Input
            placeholder={t("analyze.input")}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="md:flex-1"
          />
          <Button type="submit" disabled={importMut.isPending}>
            {importMut.isPending ? t("common.loading") : t("analyze.import")}
          </Button>
        </form>
        <FieldError>{err}</FieldError>
      </Card>

      {myReportsQ.data && myReportsQ.data.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            {locale === "de" ? "Deine letzten Berichte" : "Your recent reports"}
          </h2>
          <ul className="divide-y divide-bg-3">
            {myReportsQ.data.map((r) => (
              <li key={r.id} className="flex items-center justify-between py-2">
                <div>
                  <p className="text-sm text-zinc-100">{r.title || r.zone_name || r.wcl_code}</p>
                  <p className="text-xs text-zinc-500">{r.zone_name}</p>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setActiveReportId(r.id)}>
                  {locale === "de" ? "Öffnen" : "Open"}
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {reportQ.data && (
        <ReportView
          report={reportQ.data}
          classes={classesQ.data ?? []}
          locale={locale}
        />
      )}
    </div>
  );
}

function ReportView({
  report,
  classes,
  locale,
}: {
  report: Report;
  classes: GameClass[];
  locale: Locale;
}) {
  const [fightId, setFightId] = useState<string | null>(report.fights[0]?.id ?? null);
  const fight = report.fights.find((f) => f.id === fightId) ?? report.fights[0];
  return (
    <div className="space-y-4">
      <Card>
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{report.title || report.zone_name}</h2>
            <p className="text-xs text-zinc-500">
              <a
                href={`https://www.warcraftlogs.com/reports/${report.wcl_code}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                warcraftlogs.com/reports/{report.wcl_code}
              </a>
            </p>
          </div>
          <span className="text-xs text-zinc-500">{report.region.toUpperCase() || "—"}</span>
        </header>
        <div className="mt-4 flex flex-wrap gap-2">
          {report.fights.map((f) => (
            <button
              key={f.id}
              onClick={() => setFightId(f.id)}
              className={`rounded-md border px-3 py-1.5 text-xs ${
                f.id === fight?.id
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-bg-3 bg-bg-2 text-zinc-200 hover:border-zinc-500"
              }`}
            >
              {f.name}{" "}
              <span className="text-zinc-500">
                {f.is_kill ? "✓" : f.boss_percentage !== null ? `${f.boss_percentage?.toFixed(1)}%` : "—"}
                {f.keystone_level ? ` · +${f.keystone_level}` : ""}
              </span>
            </button>
          ))}
        </div>
      </Card>

      {fight && <PlayersTable fight={fight} classes={classes} locale={locale} reportId={report.id} />}
    </div>
  );
}

function PlayersTable({
  fight,
  classes,
  locale,
  reportId,
}: {
  fight: ReportFight;
  classes: GameClass[];
  locale: Locale;
  reportId: string;
}) {
  const t = useTranslations();
  const [activePlayerId, setActivePlayerId] = useState<string | null>(null);
  const [analysisId, setAnalysisId] = useState<string | null>(null);

  const analyzeMut = useMutation({
    mutationFn: (player: ReportPlayer) =>
      apiFetch<Analysis>("/api/v1/analyses", {
        method: "POST",
        locale,
        body: {
          report_id: reportId,
          fight_id: fight.id,
          player_id: player.id,
        },
      }),
    onSuccess: (a) => setAnalysisId(a.id),
  });

  const analysisQ = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => apiFetch<Analysis>(`/api/v1/analyses/${analysisId}`),
    enabled: !!analysisId,
  });

  return (
    <div className="space-y-4">
      <Card className="!p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-bg-2 text-xs uppercase tracking-wide text-zinc-400">
            <tr>
              <th className="px-3 py-2 text-left">{t("analyze.players")}</th>
              <th className="px-3 py-2 text-right">DPS</th>
              <th className="px-3 py-2 text-right">HPS</th>
              <th className="px-3 py-2 text-right">{t("topLogs.ilvl")}</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {fight.players.map((p) => {
              const cls = classes.find((c) => c.slug === p.class_slug);
              const spec = cls?.specs.find((s) => s.slug === p.spec_slug);
              const isActive = p.id === activePlayerId;
              return (
                <tr key={p.id} className={`border-t border-bg-3 ${isActive ? "bg-bg-2" : ""}`}>
                  <td className="px-3 py-2">
                    <div className="flex flex-col">
                      <ClassBadge cls={cls} spec={spec} locale={locale} />
                      <span className="text-xs text-zinc-400">
                        {p.name}-{p.server || "?"}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {p.dps ? formatNumber(p.dps, locale) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {p.hps ? formatNumber(p.hps, locale) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {p.item_level ? p.item_level.toFixed(0) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      size="sm"
                      onClick={() => {
                        setActivePlayerId(p.id);
                        setAnalysisId(null);
                        analyzeMut.mutate(p);
                      }}
                      disabled={analyzeMut.isPending}
                    >
                      {t("analyze.analyseThis")}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <p className="text-xs text-zinc-500">
        {t("topLogs.duration")}: {formatDuration(fight.duration_ms)}
      </p>

      {analyzeMut.isPending && (
        <Card>
          <p className="text-zinc-300">{t("analyze.analysisRunning")}</p>
        </Card>
      )}
      {analysisQ.data && <AnalysisCard analysis={analysisQ.data} locale={locale} />}
    </div>
  );
}
