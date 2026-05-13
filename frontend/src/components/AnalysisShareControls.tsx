"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Link as LinkIcon, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button, Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type { Analysis } from "@/types/api";
import type { Locale } from "@/i18n/config";

interface Props {
  analysis: Analysis;
  locale: Locale;
}

/**
 * Per-analysis share toggle. Rendered next to the analysis card in the
 * owner's view only — the public ``/share/{token}`` page never includes
 * this so anonymous viewers can't see the toggle (or worse, hit it).
 *
 * UX: one button toggles share on/off. When on, a read-only input shows
 * the full public URL with a copy-to-clipboard affordance. The state of
 * the analysis is the source of truth (``analysis.share_token`` is set
 * iff sharing is on) — we just optimistically reflect mutation responses
 * into the react-query cache.
 */
export function AnalysisShareControls({ analysis, locale }: Props) {
  const t = useTranslations();
  const qc = useQueryClient();
  const isShared = Boolean(analysis.share_token);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const url =
    typeof window !== "undefined" && analysis.share_token
      ? `${window.location.origin}/${locale}/share/${analysis.share_token}`
      : "";

  const writeBackToCache = (next: Analysis) => {
    qc.setQueryData(["analysis", next.id], next);
  };

  const enableMut = useMutation({
    mutationFn: () =>
      apiFetch<Analysis>(`/api/v1/analyses/${analysis.id}/share`, {
        method: "POST",
      }),
    onSuccess: (data) => {
      setErr(null);
      writeBackToCache(data);
    },
    onError: (e) =>
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic")),
  });

  const disableMut = useMutation({
    mutationFn: () =>
      apiFetch<Analysis>(`/api/v1/analyses/${analysis.id}/share`, {
        method: "DELETE",
      }),
    onSuccess: (data) => {
      setErr(null);
      writeBackToCache(data);
    },
    onError: (e) =>
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic")),
  });

  // Reset the "copied!" check mark a couple seconds after copy.
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(t);
  }, [copied]);

  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Best-effort — old browsers / non-https origins might block the API.
      setErr(t("analyze.share.copyFailed"));
    }
  };

  const pending = enableMut.isPending || disableMut.isPending;

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            <LinkIcon className="h-4 w-4" aria-hidden="true" />
            {t("analyze.share.title")}
          </h3>
          <p className="mt-1 text-xs text-zinc-500">
            {isShared
              ? t("analyze.share.onHint")
              : t("analyze.share.offHint")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isShared ? (
            <Button
              variant="danger"
              size="sm"
              onClick={() => disableMut.mutate()}
              disabled={pending}
              className="inline-flex items-center gap-2"
            >
              {pending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : null}
              {t("analyze.share.disable")}
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onClick={() => enableMut.mutate()}
              disabled={pending}
              className="inline-flex items-center gap-2"
            >
              {pending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : null}
              {t("analyze.share.enable")}
            </Button>
          )}
        </div>
      </div>

      {isShared && url ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            readOnly
            value={url}
            onFocus={(e) => e.currentTarget.select()}
            className="min-w-0 flex-1 rounded-md border border-bg-3 bg-bg-2 px-3 py-1.5 text-xs text-zinc-200 focus:border-accent focus:outline-none"
            aria-label={t("analyze.share.urlLabel")}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={copy}
            className="inline-flex items-center gap-2"
          >
            {copied ? (
              <Check className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Copy className="h-4 w-4" aria-hidden="true" />
            )}
            {copied ? t("analyze.share.copied") : t("analyze.share.copy")}
          </Button>
        </div>
      ) : null}

      {err ? (
        <p className="mt-2 text-xs text-red-400">{err}</p>
      ) : null}
    </Card>
  );
}
