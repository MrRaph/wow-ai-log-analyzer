"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, RotateCw, Square } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button, Card } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type { ContainerStatus, SystemStatus } from "@/types/api";

function statusColor(status: string, health: string | null): string {
  if (status === "running" && health === "healthy") return "text-emerald-300";
  if (status === "running" && health === "unhealthy") return "text-red-300";
  if (status === "running" && health === "starting") return "text-yellow-300";
  if (status === "running") return "text-emerald-300";
  if (status === "exited") return "text-zinc-400";
  if (status === "restarting") return "text-yellow-300";
  return "text-zinc-400";
}

export function SystemCard() {
  const t = useTranslations();
  const qc = useQueryClient();

  const sysQ = useQuery({
    queryKey: ["admin-system"],
    queryFn: () => apiFetch<SystemStatus>("/api/v1/admin/system"),
    // Refresh every 5 s while at least one container is in a transitional
    // state (restarting/starting). Otherwise 30 s is plenty.
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data?.enabled) return false;
      const transitional = data.containers.some(
        (c) =>
          c.status === "restarting" ||
          c.status === "created" ||
          c.health === "starting",
      );
      return transitional ? 5000 : 30000;
    },
  });

  const actionMut = useMutation({
    mutationFn: ({
      name,
      action,
    }: {
      name: string;
      action: "restart" | "start" | "stop";
    }) =>
      apiFetch<ContainerStatus>(
        `/api/v1/admin/system/containers/${name}/${action}`,
        { method: "POST" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-system"] }),
    onError: (e) => {
      window.alert(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  if (sysQ.isLoading) {
    return null; // hide until first response — avoids flash before we know enabled
  }
  // Feature switched off in backend (.env) → don't render the card at all.
  if (sysQ.data && !sysQ.data.enabled) {
    return null;
  }

  return (
    <Card>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("admin.systemTitle")}</h2>
        <span className="text-xs text-zinc-500">{sysQ.data?.project}</span>
      </div>
      <p className="mt-1 text-sm text-zinc-400">{t("admin.systemHint")}</p>

      <div className="mt-4 space-y-2">
        {(sysQ.data?.containers ?? []).map((c) => {
          const color = statusColor(c.status, c.health);
          const isRunning = c.status === "running";
          const isPending =
            actionMut.isPending && actionMut.variables?.name === c.name;
          return (
            <div
              key={c.name}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-bg-3 bg-bg-2/40 p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-zinc-100">{c.service || c.name}</span>
                  {c.is_local_ai && (
                    <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-xs text-amber-300">
                      AI
                    </span>
                  )}
                </div>
                <div className={`mt-0.5 text-xs ${color}`}>
                  {c.status}
                  {c.health ? ` · ${c.health}` : ""}
                </div>
                <div className="mt-0.5 truncate text-xs text-zinc-500" title={c.name}>
                  {c.name}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    actionMut.mutate({ name: c.name, action: "restart" })
                  }
                  disabled={isPending}
                  title={t("admin.systemRestart")}
                  aria-label={t("admin.systemRestart")}
                >
                  {isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <RotateCw className="h-4 w-4" aria-hidden="true" />
                  )}
                </Button>
                {isRunning ? (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      actionMut.mutate({ name: c.name, action: "stop" })
                    }
                    disabled={isPending}
                    title={t("admin.systemStop")}
                    aria-label={t("admin.systemStop")}
                  >
                    <Square className="h-4 w-4" aria-hidden="true" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() =>
                      actionMut.mutate({ name: c.name, action: "start" })
                    }
                    disabled={isPending}
                    title={t("admin.systemStart")}
                    aria-label={t("admin.systemStart")}
                  >
                    <Play className="h-4 w-4" aria-hidden="true" />
                  </Button>
                )}
              </div>
            </div>
          );
        })}
        {sysQ.data && sysQ.data.containers.length === 0 && (
          <p className="text-sm text-zinc-500">{t("admin.systemEmpty")}</p>
        )}
      </div>
    </Card>
  );
}
