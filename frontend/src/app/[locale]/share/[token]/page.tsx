"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { use } from "react";

import { AnalysisCard } from "@/components/AnalysisCard";
import { Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { Analysis, AnalysisPublicOut } from "@/types/api";

interface PageParams {
  locale: Locale;
  token: string;
}

/**
 * Public read of a shared analysis. NOT auth-gated — the URL token is
 * the access credential. The page is intentionally minimal: a small
 * context header (boss / player / spec) so a cold viewer knows what
 * they're looking at, then the standard ``AnalysisCard`` rendering
 * just like the owner sees it.
 */
export default function PublicSharePage({
  params,
}: {
  params: Promise<PageParams>;
}) {
  const { locale, token } = use(params);
  const t = useTranslations();

  const q = useQuery({
    queryKey: ["shared-analysis", token],
    queryFn: () =>
      apiFetch<AnalysisPublicOut>(
        `/api/v1/shared-analyses/${encodeURIComponent(token)}`,
        // Public endpoint — explicitly opt out of auth so a stale access
        // token in localStorage doesn't trigger a refresh round-trip we
        // don't need.
        { anonymous: true },
      ),
    retry: (failureCount, err) => {
      // 404 means revoked or never existed — don't keep hammering.
      if (err instanceof ApiClientError && err.status === 404) return false;
      return failureCount < 2;
    },
  });

  if (q.isLoading) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-10">
        <Card>
          <p className="text-zinc-300">{t("common.loading")}</p>
        </Card>
      </div>
    );
  }

  if (q.isError) {
    const notFound =
      q.error instanceof ApiClientError && q.error.status === 404;
    return (
      <div className="container mx-auto max-w-4xl px-4 py-10">
        <Card>
          <h1 className="text-xl font-semibold text-red-400">
            {notFound
              ? t("analyze.share.publicNotFoundTitle")
              : t("errors.generic")}
          </h1>
          <p className="mt-2 text-sm text-zinc-300">
            {notFound
              ? t("analyze.share.publicNotFoundBody")
              : (q.error instanceof ApiClientError
                  ? q.error.message
                  : String(q.error))}
          </p>
        </Card>
      </div>
    );
  }

  const data = q.data!;
  // AnalysisCard expects a full Analysis shape; the public endpoint trims
  // a handful of owner-only fields. Stub them so the card renders without
  // a type cast workaround in the card component itself.
  const cardAnalysis: Analysis = {
    id: data.id,
    status: data.status,
    locale: data.locale,
    provider: data.provider,
    model: data.model,
    summary: data.summary,
    structured: data.structured,
    error: null,
    prompt_tokens: 0,
    completion_tokens: 0,
    created_at: data.created_at,
    updated_at: data.updated_at,
    share_token: null,
  };

  const fightLabel = data.fight_name_localized || data.fight_name;
  const killBadge = data.is_kill
    ? t("analyze.kill")
    : data.boss_percentage !== null
      ? `${data.boss_percentage.toFixed(1)}%`
      : "";

  return (
    <div className="container mx-auto max-w-4xl space-y-4 px-4 py-6">
      <Card>
        <p className="text-xs uppercase tracking-wide text-zinc-500">
          {t("analyze.share.publicBanner")}
        </p>
        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold text-zinc-100">
              {data.player_name}
              {data.player_server ? `-${data.player_server}` : ""}
            </h1>
            <p className="text-sm text-zinc-400">
              {fightLabel}
              {killBadge ? (
                <span
                  className={`ml-2 font-medium ${
                    data.is_kill ? "text-emerald-400" : "text-zinc-400"
                  }`}
                >
                  {killBadge}
                </span>
              ) : null}
              {data.duration_ms > 0 ? (
                <span className="ml-2 text-zinc-500">
                  {formatDuration(data.duration_ms)}
                </span>
              ) : null}
            </p>
          </div>
          <div className="text-xs text-zinc-500">
            {formatDateTime(data.created_at, locale)}
          </div>
        </div>
      </Card>

      <AnalysisCard analysis={cardAnalysis} locale={locale} gameVersion={data.game_version} />
    </div>
  );
}
