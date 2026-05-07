"use client";

import { useTranslations } from "next-intl";

import { Card } from "@/components/ui";
import { ItemLink } from "@/components/ItemLink";
import { SeverityBadge } from "@/components/SeverityBadge";
import { SpellLink } from "@/components/SpellLink";
import { formatPercent } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { Analysis, AnalysisStructured } from "@/types/api";

interface Props {
  analysis: Analysis;
  locale: Locale;
}

export function AnalysisCard({ analysis, locale }: Props) {
  const t = useTranslations();
  if (analysis.status === "running" || analysis.status === "pending") {
    return (
      <Card>
        <p className="text-zinc-300">{t("analyze.analysisRunning")}</p>
      </Card>
    );
  }
  if (analysis.status === "failed") {
    return (
      <Card>
        <p className="text-red-400">{t("analyze.analysisFailed")}</p>
        {analysis.error && <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-400">{analysis.error}</pre>}
      </Card>
    );
  }

  const s = analysis.structured as AnalysisStructured;
  const findings = (s.findings ?? []).slice().sort((a, b) => severityRank(a.severity) - severityRank(b.severity));

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold">{s.headline ?? "—"}</h2>
          <span className="rounded-md bg-bg-3 px-3 py-1 text-sm">
            {t("analyze.score")}: <span className="font-semibold text-accent">{s.overall_score ?? "—"}</span>
          </span>
        </div>
        {s.strengths?.length ? (
          <div className="mt-4">
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-zinc-400">
              {t("analyze.strengths")}
            </h3>
            <ul className="list-disc pl-5 text-sm text-zinc-200">
              {s.strengths.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </Card>

      <Card>
        <h3 className="mb-3 text-lg font-semibold">{t("analyze.findings")}</h3>
        <div className="space-y-3">
          {findings.length === 0 && <p className="text-sm text-zinc-400">—</p>}
          {findings.map((f, i) => (
            <div
              key={i}
              className="rounded-md border border-bg-3 bg-bg-2 p-4"
              style={{
                borderColor:
                  f.severity === "critical"
                    ? "rgba(239,68,68,0.5)"
                    : f.severity === "high"
                      ? "rgba(249,115,22,0.45)"
                      : undefined,
              }}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={f.severity} />
                  <span className="text-xs text-zinc-400">{f.category}</span>
                </div>
                {f.estimated_loss_pct !== null && f.estimated_loss_pct !== undefined && (
                  <span className="text-xs text-zinc-300">
                    {t("analyze.estimatedLoss")}: {formatPercent(f.estimated_loss_pct, locale)}
                  </span>
                )}
              </div>
              <h4 className="mt-2 text-base font-semibold text-zinc-100">{f.title}</h4>
              <p className="mt-1 whitespace-pre-line text-sm text-zinc-200">{f.detail}</p>
              {(f.related_spell_ids?.length || f.related_item_ids?.length) ? (
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {f.related_spell_ids?.map((id) => (
                    <SpellLink key={`s-${id}`} spellId={id} locale={locale} />
                  ))}
                  {f.related_item_ids?.map((id) => (
                    <ItemLink key={`i-${id}`} itemId={id} locale={locale} />
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {textBlock(t("analyze.rotation"), s.rotation_summary)}
        {textBlock(t("analyze.cooldowns"), s.cooldown_usage_summary)}
        {textBlock(t("analyze.stats"), s.stat_recommendations)}
        {textBlock(t("analyze.talents"), s.talent_recommendations)}
        {textBlock(t("analyze.gearTrinkets"), s.gear_and_trinket_notes)}
        {textBlock(t("analyze.comparison"), s.comparison_to_top_logs)}
      </div>
    </div>
  );
}

function severityRank(s: string): number {
  return ({ critical: 0, high: 1, medium: 2, low: 3, info: 4 } as Record<string, number>)[s] ?? 5;
}

function textBlock(title: string, body: string | undefined) {
  if (!body) return null;
  return (
    <Card>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">{title}</h3>
      <p className="whitespace-pre-line text-sm text-zinc-200">{body}</p>
    </Card>
  );
}
