"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button, Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type { SimcStatus } from "@/types/api";

export function SimcCard() {
  const t = useTranslations();
  const qc = useQueryClient();

  const statusQ = useQuery({
    queryKey: ["admin-simc-status"],
    queryFn: () => apiFetch<SimcStatus>("/api/v1/admin/simc/status"),
    // Refetch every 30s while the container is in a transitional state, else
    // a lazy 2 min — admins don't need millisecond freshness here.
    refetchInterval: (q) => {
      const c = q.state.data?.container;
      if (c && (c.status === "restarting" || c.health === "starting")) return 5000;
      return 120000;
    },
  });

  const updateMut = useMutation({
    mutationFn: () =>
      apiFetch<SimcStatus>("/api/v1/admin/simc/update", { method: "POST" }),
    onSuccess: (s) => {
      qc.setQueryData(["admin-simc-status"], s);
      qc.invalidateQueries({ queryKey: ["admin-system"] });
    },
  });

  const data = statusQ.data;
  const banner = data?.build_banner || "";
  const reachable = data?.reachable ?? false;
  const errMsg =
    updateMut.error instanceof ApiClientError
      ? updateMut.error.message
      : updateMut.error
        ? t("errors.generic")
        : null;

  return (
    <Card>
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("adminSimc.title")}</h2>
        <span
          className={`text-xs ${reachable ? "text-emerald-300" : "text-zinc-400"}`}
        >
          {reachable ? t("adminSimc.ready") : t("adminSimc.unreachable")}
        </span>
      </header>
      <p className="mb-3 text-xs text-zinc-500">{t("adminSimc.hint")}</p>

      <dl className="mb-4 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase text-zinc-500">
            {t("adminSimc.baseUrl")}
          </dt>
          <dd className="font-mono text-xs text-zinc-200">
            {data?.base_url || "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-zinc-500">
            {t("adminSimc.build")}
          </dt>
          <dd className="font-mono text-xs text-zinc-200 break-all">
            {banner || "—"}
          </dd>
        </div>
        {data?.container && (
          <>
            <div>
              <dt className="text-xs uppercase text-zinc-500">
                {t("adminSimc.containerImage")}
              </dt>
              <dd className="font-mono text-xs text-zinc-200 break-all">
                {data.container.image}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-zinc-500">
                {t("adminSimc.containerStatus")}
              </dt>
              <dd className="text-xs text-zinc-200">
                {data.container.status}
                {data.container.health ? ` (${data.container.health})` : ""}
              </dd>
            </div>
          </>
        )}
      </dl>

      <Button
        type="button"
        onClick={() => updateMut.mutate()}
        disabled={updateMut.isPending}
        className="inline-flex items-center gap-2"
      >
        {updateMut.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        {updateMut.isPending
          ? t("adminSimc.updating")
          : t("adminSimc.updateNow")}
      </Button>
      {errMsg && (
        <p className="mt-2 text-xs text-red-300">{errMsg}</p>
      )}
    </Card>
  );
}
