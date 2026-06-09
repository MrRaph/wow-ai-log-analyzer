"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo } from "react";

import { Card } from "@/components/ui";
import { ItemLink } from "@/components/ItemLink";
import { ProseWithLinks, hasInlineRefs } from "@/components/ProseWithLinks";
import { SeverityBadge } from "@/components/SeverityBadge";
import { SpellLink } from "@/components/SpellLink";
import { formatPercent } from "@/lib/format";
import { formatParsePercent, parseColorFor } from "@/lib/parsePercent";
import type { Locale } from "@/i18n/config";
import type { Analysis, AnalysisStructured } from "@/types/api";

interface Props {
  analysis: Analysis;
  locale: Locale;
  gameVersion?: string;
}

export function AnalysisCard({ analysis, locale, gameVersion }: Props) {
  const t = useTranslations();

  const structured = (analysis.structured ?? {}) as AnalysisStructured;
  // Local name lookup ({"spell:115151": "Erneuernder Nebel", ...}) the
  // backend stores alongside the AI output. Used as a friendly display label
  // for the spell/item chips even when ad blockers stop wowhead's tooltip
  // script from auto-renaming the link.
  const nameMap = structured._localized_names ?? {};
  // ``_talent_spell_ids`` is the per-analysis lookup the backend ships so
  // we can render ``[Label](talent:<traitNodeEntryId>)`` markdown links
  // as Wowhead spell links. WCL ships TraitNodeEntry IDs which collide
  // with old MoP spell IDs, so we MUST resolve to the underlying spell
  // ID before linking.
  const talentSpellIds = structured._talent_spell_ids ?? {};
  const parseMetrics = structured._parse_metrics;

  // Wowhead's tooltip script (loaded once at the layout level) only scans
  // the DOM at boot. AnalysisCard renders dynamically after the AI returns,
  // so we have to manually nudge the script to attach tooltips + rewrite
  // labels. The script may itself still be loading when this effect runs,
  // so we retry a few times before giving up.
  useEffect(() => {
    if (analysis.status !== "succeeded") return;
    if (typeof window === "undefined") return;
    let attempts = 0;
    let cancelled = false;
    const tryRefresh = () => {
      if (cancelled) return;
      const wh = window.$WowheadPower;
      if (wh && typeof wh.refreshLinks === "function") {
        wh.refreshLinks();
        return;
      }
      attempts += 1;
      if (attempts < 20) {
        // 20 × 250 ms = 5 s total — covers a slow wowhead script load.
        window.setTimeout(tryRefresh, 250);
      }
    };
    const timer = window.setTimeout(tryRefresh, 50);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [analysis.id, analysis.status]);

  const findings = useMemo(() => {
    return (structured.findings ?? [])
      .slice()
      .sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  }, [structured.findings]);

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
        {analysis.error && (
          <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-400">{analysis.error}</pre>
        )}
      </Card>
    );
  }

  const s = structured;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-xl font-semibold">
            <ProseWithLinks
              text={s.headline ?? "—"}
              locale={locale}
              nameMap={nameMap}
              talentSpellIds={talentSpellIds}
              gameVersion={gameVersion}
              className=""
            />
          </h2>
          <div className="flex flex-wrap items-baseline gap-2">
            {parseMetrics?.parse_percent !== null && parseMetrics?.parse_percent !== undefined ? (
              <span
                className="rounded-md px-3 py-1 text-sm"
                style={{
                  backgroundColor: parseColorFor(parseMetrics.parse_percent).background,
                  color: parseColorFor(parseMetrics.parse_percent).foreground,
                }}
                title={t("analyze.parseTooltip")}
              >
                {t("analyze.parsePercent")}:{" "}
                <span className="font-semibold">
                  {formatParsePercent(parseMetrics.parse_percent)}
                </span>
              </span>
            ) : null}
            {parseMetrics?.ilvl_percent !== null && parseMetrics?.ilvl_percent !== undefined ? (
              <span
                className="rounded-md px-3 py-1 text-sm"
                style={{
                  backgroundColor: parseColorFor(parseMetrics.ilvl_percent).background,
                  color: parseColorFor(parseMetrics.ilvl_percent).foreground,
                }}
                title={t("analyze.ilvlTooltip")}
              >
                {t("analyze.ilvlPercent")}:{" "}
                <span className="font-semibold">
                  {formatParsePercent(parseMetrics.ilvl_percent)}
                </span>
              </span>
            ) : null}
            <span className="rounded-md bg-bg-3 px-3 py-1 text-sm">
              {t("analyze.score")}:{" "}
              <span className="font-semibold text-accent">{s.overall_score ?? "—"}</span>
            </span>
          </div>
        </div>
        {s.strengths?.length ? (
          <div className="mt-4">
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-zinc-400">
              {t("analyze.strengths")}
            </h3>
            <ul className="list-disc pl-5 text-sm text-zinc-200">
              {s.strengths.map((line, i) => (
                <li key={i}>
                  <ProseWithLinks
                    text={line}
                    locale={locale}
                    nameMap={nameMap}
                    talentSpellIds={talentSpellIds}
                    gameVersion={gameVersion}
                    className=""
                  />
                </li>
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
              <h4 className="mt-2 text-base font-semibold text-zinc-100">
                <ProseWithLinks
                  text={f.title}
                  locale={locale}
                  nameMap={nameMap}
                  talentSpellIds={talentSpellIds}
                  gameVersion={gameVersion}
                  className=""
                />
              </h4>
              <ProseWithLinks
                text={f.detail}
                locale={locale}
                nameMap={nameMap}
                talentSpellIds={talentSpellIds}
                gameVersion={gameVersion}
                className="mt-1 text-sm text-zinc-200"
              />
              {/* Chip list only as a fallback for legacy analyses without
                  inline markdown links in their prose — modern outputs
                  render the links inline above and the chips become
                  redundant. */}
              {!hasInlineRefs(f.detail) &&
              (f.related_spell_ids?.length || f.related_item_ids?.length) ? (
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {f.related_spell_ids?.map((id) => (
                    <SpellLink
                      key={`s-${id}`}
                      spellId={id}
                      locale={locale}
                      fallback={nameMap[`spell:${id}`]}
                      gameVersion={gameVersion}
                    />
                  ))}
                  {f.related_item_ids?.map((id) => (
                    <ItemLink
                      key={`i-${id}`}
                      itemId={id}
                      locale={locale}
                      fallback={nameMap[`item:${id}`]}
                      gameVersion={gameVersion}
                    />
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {proseBlock(t("analyze.rotation"), s.rotation_summary, locale, nameMap, talentSpellIds, gameVersion)}
        {proseBlock(t("analyze.cooldowns"), s.cooldown_usage_summary, locale, nameMap, talentSpellIds, gameVersion)}
        {proseBlock(t("analyze.stats"), s.stat_recommendations, locale, nameMap, talentSpellIds, gameVersion)}
        {proseBlock(t("analyze.talents"), s.talent_recommendations, locale, nameMap, talentSpellIds, gameVersion)}
        {proseBlock(t("analyze.gearTrinkets"), s.gear_and_trinket_notes, locale, nameMap, talentSpellIds, gameVersion)}
        {proseBlock(t("analyze.comparison"), s.comparison_to_top_logs, locale, nameMap, talentSpellIds, gameVersion)}
      </div>
    </div>
  );
}

function severityRank(s: string): number {
  return ({ critical: 0, high: 1, medium: 2, low: 3, info: 4 } as Record<string, number>)[s] ?? 5;
}

function proseBlock(
  title: string,
  body: string | undefined,
  locale: Locale,
  nameMap: Record<string, string>,
  talentSpellIds: Record<string, number>,
  gameVersion?: string,
) {
  if (!body) return null;
  return (
    <Card>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">{title}</h3>
      <ProseWithLinks
        text={body}
        locale={locale}
        nameMap={nameMap}
        talentSpellIds={talentSpellIds}
        gameVersion={gameVersion}
      />
    </Card>
  );
}
