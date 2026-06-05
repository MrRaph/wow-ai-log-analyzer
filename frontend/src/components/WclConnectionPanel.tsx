"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button, Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { WclAuthorizationStart, WclConnectionStatus } from "@/types/api";

type WclFlavor = "retail" | "fresh";

export function WclConnectionPanel({ locale, flavor }: { locale: Locale; flavor: WclFlavor }) {
  const t = useTranslations();
  const qc = useQueryClient();
  const search = useSearchParams();
  const [flash, setFlash] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const statusQ = useQuery({
    queryKey: ["wcl-connection", flavor],
    queryFn: () =>
      apiFetch<WclConnectionStatus>(`/api/v1/users/me/wcl-connection?flavor=${flavor}`),
  });

  const startPath = flavor === "fresh" ? "/api/v1/auth/wcl-fresh/start" : "/api/v1/auth/wcl/start";
  const callbackSuccess = flavor === "fresh" ? "connected-fresh" : "connected";

  const startMut = useMutation({
    mutationFn: () => apiFetch<WclAuthorizationStart>(startPath, { method: "POST" }),
    onSuccess: (data) => {
      window.location.href = data.authorization_url;
    },
    onError: (e) =>
      setFlash({
        kind: "error",
        text:
          e instanceof ApiClientError
            ? e.message
            : t("profile.wclConnectError", { reason: "unknown" }),
      }),
  });

  const disconnectMut = useMutation({
    mutationFn: () => apiFetch(`/api/v1/users/me/wcl-connection?flavor=${flavor}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wcl-connection", flavor] }),
  });

  useEffect(() => {
    const result = search.get("wcl");
    if (result === callbackSuccess) {
      setFlash({ kind: "ok", text: t("admin.saved") });
      qc.invalidateQueries({ queryKey: ["wcl-connection", flavor] });
    } else if (result === "error") {
      const reason = search.get("reason") ?? "unknown";
      setFlash({ kind: "error", text: t("profile.wclConnectError", { reason }) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, flavor]);

  const status = statusQ.data;
  const connectedLabel = status?.wcl_user_name
    ? t("profile.wclConnectedAs", { name: status.wcl_user_name })
    : t("profile.wclConnectedNoName");
  const sectionTitle =
    flavor === "fresh" ? t("profile.wclFreshSection") : t("profile.wclSection");
  const sectionHelp =
    flavor === "fresh" ? t("profile.wclFreshSectionHelp") : t("profile.wclSectionHelp");

  return (
    <Card>
      <h2 className="mb-2 font-semibold">{sectionTitle}</h2>
      <p className="mb-3 text-sm text-zinc-400">{sectionHelp}</p>

      {flash && (
        <p
          className={`mb-3 rounded p-2 text-sm ${
            flash.kind === "ok"
              ? "bg-emerald-500/10 text-emerald-300"
              : "bg-red-500/10 text-red-300"
          }`}
        >
          {flash.text}
        </p>
      )}

      {!status ? (
        <p className="text-sm text-zinc-500">{t("common.loading")}</p>
      ) : status.connected ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-zinc-100">{connectedLabel}</p>
            {status.expires_at && (
              <p className="text-xs text-zinc-500">
                {locale === "de" ? "Token läuft ab am" : "Token expires"}: {" "}
                {formatDateTime(status.expires_at, locale)}
              </p>
            )}
          </div>
          <Button
            variant="secondary"
            onClick={() => disconnectMut.mutate()}
            disabled={disconnectMut.isPending}
          >
            {t("profile.wclDisconnect")}
          </Button>
        </div>
      ) : (
        <Button onClick={() => startMut.mutate()} disabled={startMut.isPending}>
          {startMut.isPending ? t("common.loading") : t("profile.wclConnect")}
        </Button>
      )}
    </Card>
  );
}
