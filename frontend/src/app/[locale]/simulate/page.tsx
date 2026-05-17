"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Sparkles, Sword, Trash2, Wand2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { use, useEffect, useMemo, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { EmptyState } from "@/components/EmptyState";
import { Button, Card, FieldError, Input, Label } from "@/components/ui";
import type { Locale } from "@/i18n/config";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type {
  PaginatedSimulations,
  SidecarStatus,
  SimcFightProfile,
  SimcRotation,
  Simulation,
  SimulationInfo,
  SimulationLoadoutIn,
  SimulationRunOut,
} from "@/types/api";

const FIGHT_PROFILES: SimcFightProfile[] = ["single_target", "council", "mythic_plus"];
const ROTATIONS: SimcRotation[] = ["simc_default", "blizzard", "custom"];
const PRECISIONS = ["fast", "medium", "precise"] as const;
type Precision = (typeof PRECISIONS)[number];

export default function SimulatePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  return <AuthGuard locale={locale}>{() => <SimulateView locale={locale} />}</AuthGuard>;
}

function SimulateView({ locale }: { locale: Locale }) {
  const t = useTranslations();
  const qc = useQueryClient();

  const infoQ = useQuery({
    queryKey: ["simulation-info"],
    queryFn: () => apiFetch<SimulationInfo>("/api/v1/simulations/_info"),
    refetchOnWindowFocus: false,
  });

  const [profile, setProfile] = useState("");
  const [label, setLabel] = useState("");
  const [selectedFights, setSelectedFights] = useState<SimcFightProfile[]>([
    "single_target",
  ]);
  const [selectedRotations, setSelectedRotations] = useState<SimcRotation[]>([
    "simc_default",
  ]);
  const [loadouts, setLoadouts] = useState<SimulationLoadoutIn[]>([
    { name: "", talents: "" },
  ]);
  const [precision, setPrecision] = useState<Precision>("precise");
  const [activeSimulationId, setActiveSimulationId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const maxLoadouts = infoQ.data?.max_loadouts ?? 3;

  const myListQ = useQuery({
    queryKey: ["my-simulations"],
    queryFn: () =>
      apiFetch<PaginatedSimulations>("/api/v1/simulations?page=1&page_size=20"),
    refetchInterval: (q) =>
      q.state.data?.items.some(
        (s) => s.status === "pending" || s.status === "running",
      )
        ? 2500
        : false,
  });

  const detailQ = useQuery({
    queryKey: ["simulation", activeSimulationId],
    queryFn: () =>
      apiFetch<Simulation>(`/api/v1/simulations/${activeSimulationId}`),
    enabled: !!activeSimulationId,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "pending" || s === "running" ? 2000 : false;
    },
  });

  const createMut = useMutation({
    mutationFn: () =>
      apiFetch<Simulation>("/api/v1/simulations", {
        method: "POST",
        body: {
          label,
          simc_profile: profile,
          fight_profiles: selectedFights,
          rotations: selectedRotations,
          loadouts,
          precision,
        },
      }),
    onSuccess: (sim) => {
      setErr(null);
      setActiveSimulationId(sim.id);
      qc.invalidateQueries({ queryKey: ["my-simulations"] });
    },
    onError: (e) => {
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/simulations/${id}`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      if (activeSimulationId === id) setActiveSimulationId(null);
      qc.invalidateQueries({ queryKey: ["my-simulations"] });
    },
  });

  useEffect(() => {
    const s = detailQ.data?.status;
    if (s === "succeeded" || s === "failed") {
      qc.invalidateQueries({ queryKey: ["my-simulations"] });
    }
  }, [detailQ.data?.status, qc]);

  function toggleFight(f: SimcFightProfile) {
    setSelectedFights((prev) =>
      prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f],
    );
  }
  function toggleRotation(r: SimcRotation) {
    setSelectedRotations((prev) =>
      prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r],
    );
  }

  function updateLoadout(i: number, patch: Partial<SimulationLoadoutIn>) {
    setLoadouts((prev) =>
      prev.map((ld, idx) => (idx === i ? { ...ld, ...patch } : ld)),
    );
  }
  function addLoadout() {
    if (loadouts.length >= maxLoadouts) return;
    setLoadouts((prev) => [...prev, { name: "", talents: "" }]);
  }
  function removeLoadout(i: number) {
    setLoadouts((prev) => prev.filter((_, idx) => idx !== i));
  }

  const submitDisabled =
    !profile.trim() ||
    selectedFights.length === 0 ||
    selectedRotations.length === 0 ||
    loadouts.length === 0 ||
    createMut.isPending;

  const sidecarBadge = infoQ.data
    ? infoQ.data.sidecar_reachable
      ? infoQ.data.simc_build || t("simulate.sidecarReady")
      : t("simulate.sidecarUnreachable")
    : "";

  const precisionIterMap = useMemo(() => {
    const m: Record<string, number> = {};
    for (const p of infoQ.data?.precisions ?? []) m[p.key] = p.iterations;
    return m;
  }, [infoQ.data]);

  const totalRuns =
    selectedFights.length * selectedRotations.length * loadouts.length;

  return (
    <div className="container-page space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold">{t("simulate.title")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">{t("simulate.subtitle")}</p>
        {sidecarBadge && (
          <p className="mt-1 text-xs text-zinc-500">
            <Sparkles className="mr-1 inline h-3 w-3" />
            {sidecarBadge}
          </p>
        )}
      </header>

      <Card className="space-y-4">
        <div>
          <Label htmlFor="sim-label">{t("simulate.labelInputLabel")}</Label>
          <Input
            id="sim-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={t("simulate.labelInputPlaceholder")}
            maxLength={200}
          />
        </div>

        <div>
          <Label htmlFor="sim-profile">{t("simulate.profileLabel")}</Label>
          <p className="mb-1 text-xs text-zinc-500">{t("simulate.profileHint")}</p>
          <textarea
            id="sim-profile"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            placeholder="paladin&#10;level=80&#10;race=blood_elf&#10;..."
            spellCheck={false}
            className="h-48 w-full rounded-md border border-bg-3 bg-bg-2 px-3 py-2 font-mono text-xs text-zinc-100 placeholder:text-zinc-500 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
          />
        </div>

        <div>
          <Label>{t("simulate.fightProfilesLabel")}</Label>
          <div className="flex flex-wrap gap-2">
            {FIGHT_PROFILES.map((fp) => {
              const meta = infoQ.data?.fight_profiles.find((p) => p.key === fp);
              const labelText = locale === "de" ? meta?.label_de : meta?.label_en;
              const active = selectedFights.includes(fp);
              return (
                <button
                  key={fp}
                  type="button"
                  onClick={() => toggleFight(fp)}
                  className={`rounded-md border px-3 py-2 text-xs ${
                    active
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-bg-3 bg-bg-2 text-zinc-300 hover:border-zinc-500"
                  }`}
                >
                  <span className="font-medium">
                    {labelText || t(`simulate.fightProfile.${fp}`)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <Label>{t("simulate.rotationModesLabel")}</Label>
          <p className="mb-2 text-xs text-zinc-500">{t("simulate.rotationModesHint")}</p>
          <div className="flex flex-wrap gap-2">
            {ROTATIONS.map((r) => {
              const active = selectedRotations.includes(r);
              return (
                <button
                  key={r}
                  type="button"
                  onClick={() => toggleRotation(r)}
                  className={`rounded-md border px-3 py-2 text-left text-xs ${
                    active
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-bg-3 bg-bg-2 text-zinc-300 hover:border-zinc-500"
                  }`}
                >
                  <div className="font-medium">{t(`simulate.rotation.${r}`)}</div>
                  <div className="mt-0.5 text-[10px] text-zinc-500 max-w-[280px]">
                    {t(`simulate.rotationHint.${r}`)}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <Label>{t("simulate.precisionLabel")}</Label>
          <div className="flex flex-wrap gap-2">
            {PRECISIONS.map((p) => {
              const active = precision === p;
              const iter = precisionIterMap[p];
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPrecision(p)}
                  className={`rounded-md border px-3 py-2 text-xs ${
                    active
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-bg-3 bg-bg-2 text-zinc-300 hover:border-zinc-500"
                  }`}
                >
                  <div className="font-medium">{t(`simulate.precision.${p}`)}</div>
                  <div className="mt-0.5 text-[10px] text-zinc-500">
                    {iter ? `${iter} ${t("simulate.iterationsWord")}` : ""}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <Label>{t("simulate.loadoutsLabel")}</Label>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={addLoadout}
              disabled={loadouts.length >= maxLoadouts}
              className="inline-flex items-center gap-1"
            >
              <Plus className="h-3.5 w-3.5" />
              {t("simulate.addLoadout")}
            </Button>
          </div>
          <p className="mb-2 text-xs text-zinc-500">
            {t("simulate.loadoutsHint", { max: maxLoadouts })}
          </p>
          <div className="space-y-3">
            {loadouts.map((ld, i) => (
              <div
                key={i}
                className="rounded-md border border-bg-3 bg-bg-2/40 p-3 space-y-2"
              >
                <div className="flex flex-wrap items-end gap-3">
                  <div className="flex-1 min-w-[200px]">
                    <Label htmlFor={`ld-name-${i}`}>{t("simulate.loadoutName")}</Label>
                    <Input
                      id={`ld-name-${i}`}
                      value={ld.name}
                      onChange={(e) => updateLoadout(i, { name: e.target.value })}
                      placeholder={t("simulate.loadoutNamePlaceholder", { n: i + 1 })}
                      maxLength={120}
                    />
                  </div>
                  {loadouts.length > 1 && (
                    <Button
                      type="button"
                      size="sm"
                      variant="danger"
                      onClick={() => removeLoadout(i)}
                      title={t("simulate.removeLoadout")}
                      aria-label={t("simulate.removeLoadout")}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
                <div>
                  <Label htmlFor={`ld-talents-${i}`}>{t("simulate.talentsLabel")}</Label>
                  <p className="mb-1 text-xs text-zinc-500">{t("simulate.talentsHint")}</p>
                  <textarea
                    id={`ld-talents-${i}`}
                    value={ld.talents}
                    onChange={(e) => updateLoadout(i, { talents: e.target.value })}
                    placeholder="talents=..."
                    spellCheck={false}
                    className="h-24 w-full rounded-md border border-bg-3 bg-bg-2 px-3 py-2 font-mono text-xs text-zinc-100 placeholder:text-zinc-500 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <FieldError>{err}</FieldError>
        <div className="flex flex-wrap items-center gap-4">
          <Button
            type="button"
            onClick={() => createMut.mutate()}
            disabled={submitDisabled}
            className="inline-flex items-center gap-2"
          >
            {createMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            <Wand2 className="h-4 w-4" />
            {createMut.isPending ? t("simulate.starting") : t("simulate.runSimulation")}
          </Button>
          {totalRuns > 0 && (
            <span className="text-xs text-zinc-500">
              {t("simulate.totalRuns", { n: totalRuns })}
            </span>
          )}
        </div>
      </Card>

      {activeSimulationId && detailQ.data && (
        <SimulationDetail simulation={detailQ.data} locale={locale} />
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">
          {t("simulate.history")}
        </h2>
        {myListQ.isLoading && <p className="text-sm text-zinc-500">{t("common.loading")}</p>}
        {!myListQ.isLoading && (myListQ.data?.items.length ?? 0) === 0 && (
          <EmptyState message={t("simulate.historyEmpty")} />
        )}
        <ul className="divide-y divide-bg-3">
          {myListQ.data?.items.map((item) => {
            const isActive = item.id === activeSimulationId;
            const isDeleting = deleteMut.isPending && deleteMut.variables === item.id;
            return (
              <li
                key={item.id}
                className={`flex flex-wrap items-center justify-between gap-3 py-2 ${
                  isActive ? "-mx-3 rounded-md bg-bg-2/40 px-3" : ""
                }`}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-100">
                    {item.label || t("simulate.untitled")}{" "}
                    <span className="ml-2 text-xs text-zinc-500">
                      {t(`simulate.status.${item.status}`)}
                    </span>
                  </p>
                  <p className="text-xs text-zinc-500">
                    {formatDateTime(item.created_at, locale)} ·{" "}
                    {item.loadout_count} × {item.fight_profiles.length} × {item.rotations.length}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    size="sm"
                    variant={isActive ? "ghost" : "secondary"}
                    onClick={() => setActiveSimulationId(isActive ? null : item.id)}
                  >
                    {isActive ? t("common.cancel") : t("simulate.openResult")}
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      if (window.confirm(t("simulate.confirmDelete"))) {
                        deleteMut.mutate(item.id);
                      }
                    }}
                    disabled={isDeleting}
                    aria-label={t("simulate.delete")}
                    title={t("simulate.delete")}
                  >
                    {isDeleting ? "…" : <Trash2 className="h-4 w-4" />}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

function SimulationDetail({ simulation, locale }: { simulation: Simulation; locale: Locale }) {
  const t = useTranslations();
  const runs = simulation.runs;
  const isWorking = simulation.status === "pending" || simulation.status === "running";

  // Sidecar queue hint — only fetched while this sim is queued *and*
  // nothing of ours is running yet, so we don't spam the endpoint
  // once execution has actually started.
  const allPending =
    isWorking && runs.length > 0 && runs.every((r) => r.status === "pending");
  const sidecarQ = useQuery({
    queryKey: ["sidecar-status"],
    queryFn: () => apiFetch<SidecarStatus>("/api/v1/simulations/_sidecar-status"),
    enabled: allPending,
    refetchInterval: allPending ? 5000 : false,
  });

  // Overall progress for the run grid: how many cells have reached a
  // terminal state. The bar is responsive to per-run completions so
  // "5 of 12 done" updates in real time without a per-iteration probe
  // on the sidecar.
  const total = runs.length;
  const done = runs.filter(
    (r) => r.status === "succeeded" || r.status === "failed",
  ).length;
  const running = runs.filter((r) => r.status === "running").length;
  const pendingCount = runs.filter((r) => r.status === "pending").length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  // Lookup grid keyed by (loadout_index, fight, rotation) so we can address
  // every cell in O(1) when rendering the comparison matrix.
  const grid = useMemo(() => {
    const m = new Map<string, SimulationRunOut>();
    for (const r of runs) m.set(`${r.loadout_index}::${r.fight_profile_key}::${r.rotation}`, r);
    return m;
  }, [runs]);

  const winner = useMemo(() => {
    const ok = runs.filter((r) => r.status === "succeeded");
    if (ok.length === 0) return null;
    return ok.reduce((a, b) => (a.dps_mean >= b.dps_mean ? a : b));
  }, [runs]);

  // Tally how many ``column groups`` we render. Each fight_profile spans
  // ``rotations.length`` sub-columns when > 1 rotation is being compared,
  // otherwise just 1.
  const showRotationAxis = simulation.rotations.length > 1;

  return (
    <Card className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{simulation.label || t("simulate.untitled")}</h2>
          <p className="text-xs text-zinc-500">
            {t(`simulate.status.${simulation.status}`)} · {t(`simulate.precision.${simulation.precision}`)} ({simulation.iterations} {t("simulate.iterationsWord")})
            {simulation.simc_build && (
              <>
                {" · "}
                <span className="text-zinc-400">{simulation.simc_build}</span>
              </>
            )}
          </p>
        </div>
        {isWorking && (
          <span className="inline-flex items-center gap-2 text-xs text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t("simulate.working")}
          </span>
        )}
      </header>

      {isWorking && total > 0 && (
        <div>
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>
              {t("simulate.progressRuns", { done, total })}
              {running > 0 && (
                <span className="ml-2 text-zinc-500">
                  ({t("simulate.progressRunning", { n: running })})
                </span>
              )}
            </span>
            <span className="tabular-nums">{pct}%</span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-bg-3">
            <div
              className="h-full bg-accent transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          {allPending && sidecarQ.data?.reachable && (
            <p className="mt-2 text-xs text-zinc-500">
              {sidecarQ.data.running > 0 || sidecarQ.data.queued > pendingCount
                ? t("simulate.queueHint", {
                    queued: sidecarQ.data.queued,
                    running: sidecarQ.data.running,
                  })
                : t("simulate.queueWaitingForWorker")}
            </p>
          )}
        </div>
      )}

      {simulation.error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/5 p-2 text-sm text-red-300">
          {simulation.error}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-bg-2 text-xs uppercase tracking-wide text-zinc-400">
            <tr>
              <th rowSpan={showRotationAxis ? 2 : 1} className="px-3 py-2 text-left">
                {t("simulate.loadoutCol")}
              </th>
              {simulation.fight_profiles.map((fp) => (
                <th
                  key={fp}
                  colSpan={showRotationAxis ? simulation.rotations.length : 1}
                  className="px-3 py-2 text-right border-l border-bg-3"
                >
                  {t(`simulate.fightProfile.${fp}`)}
                </th>
              ))}
            </tr>
            {showRotationAxis && (
              <tr>
                {simulation.fight_profiles.flatMap((fp) =>
                  simulation.rotations.map((rot, idx) => (
                    <th
                      key={`${fp}-${rot}`}
                      className={`px-3 py-1.5 text-right text-[11px] font-normal ${idx === 0 ? "border-l border-bg-3" : ""}`}
                    >
                      {t(`simulate.rotation.${rot}`)}
                    </th>
                  )),
                )}
              </tr>
            )}
          </thead>
          <tbody>
            {simulation.loadouts.map((ld, li) => (
              <tr key={li} className="border-t border-bg-3">
                <td className="px-3 py-2">
                  <span className="font-medium text-zinc-100">
                    {ld.name || t("simulate.loadoutNamePlaceholder", { n: li + 1 })}
                  </span>
                </td>
                {simulation.fight_profiles.flatMap((fp) =>
                  simulation.rotations.map((rot, idx) => {
                    const run = grid.get(`${li}::${fp}::${rot}`);
                    return (
                      <RunCell
                        key={`${fp}-${rot}`}
                        run={run}
                        locale={locale}
                        isWinner={!!winner && run?.id === winner.id}
                        firstInGroup={idx === 0}
                      />
                    );
                  }),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-3">
        {runs.map((run) => (
          <RunBreakdown key={run.id} run={run} simulation={simulation} locale={locale} />
        ))}
      </div>
    </Card>
  );
}

function RunCell({
  run,
  locale,
  isWinner,
  firstInGroup,
}: {
  run: SimulationRunOut | undefined;
  locale: Locale;
  isWinner: boolean;
  firstInGroup: boolean;
}) {
  const t = useTranslations();
  const borderCls = firstInGroup ? "border-l border-bg-3" : "";
  if (!run) {
    return <td className={`px-3 py-2 text-right text-zinc-500 ${borderCls}`}>—</td>;
  }
  if (run.status === "succeeded") {
    return (
      <td className={`px-3 py-2 text-right tabular-nums ${borderCls}`}>
        <span
          className={`font-semibold ${isWinner ? "text-amber-300" : "text-zinc-100"}`}
        >
          {formatNumber(run.dps_mean, locale)}
        </span>
        {isWinner && (
          <span className="ml-1 inline-flex items-center text-xs text-amber-300">
            <Sword className="h-3 w-3" />
          </span>
        )}
        <div className="text-xs text-zinc-500">±{formatNumber(run.dps_stddev, locale)}</div>
      </td>
    );
  }
  if (run.status === "failed") {
    return (
      <td className={`px-3 py-2 text-right text-xs text-red-300 ${borderCls}`}>
        {t("simulate.runFailed")}
      </td>
    );
  }
  return (
    <td className={`px-3 py-2 text-right text-xs text-zinc-400 ${borderCls}`}>
      <Loader2 className="ml-auto h-4 w-4 animate-spin" />
    </td>
  );
}

function RunBreakdown({
  run,
  simulation,
  locale,
}: {
  run: SimulationRunOut;
  simulation: Simulation;
  locale: Locale;
}) {
  const t = useTranslations();
  if (run.status !== "succeeded") {
    if (run.status === "failed") {
      return (
        <details className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm">
          <summary className="cursor-pointer text-red-300">
            {runHeader(run, simulation, t, locale)} — {t("simulate.runFailed")}
          </summary>
          {run.error && (
            <pre className="mt-2 whitespace-pre-wrap text-xs text-zinc-400">
              {run.error}
            </pre>
          )}
        </details>
      );
    }
    return null;
  }
  const top = run.abilities.slice(0, 15);
  return (
    <details className="rounded-md border border-bg-3 bg-bg-2/40 p-3">
      <summary className="cursor-pointer text-sm font-medium text-zinc-100">
        {runHeader(run, simulation, t, locale)}
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-2 py-1 text-left">{t("simulate.abilityCol")}</th>
              <th className="px-2 py-1 text-right">DPS</th>
              <th className="px-2 py-1 text-right">%</th>
              <th className="px-2 py-1 text-right">{t("simulate.executesCol")}</th>
            </tr>
          </thead>
          <tbody>
            {top.map((a, i) => (
              <tr key={`${a.name}-${i}`} className="border-t border-bg-3">
                <td className="px-2 py-1">{a.name}</td>
                <td className="px-2 py-1 text-right tabular-nums">
                  {formatNumber(a.dps, locale)}
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-zinc-400">
                  {a.pct.toFixed(1)}%
                </td>
                <td className="px-2 py-1 text-right tabular-nums text-zinc-500">
                  {formatNumber(a.executes, locale)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function runHeader(
  run: SimulationRunOut,
  simulation: Simulation,
  t: ReturnType<typeof useTranslations>,
  locale: Locale,
) {
  const loadout = simulation.loadouts[run.loadout_index];
  const ldName =
    loadout?.name ||
    t("simulate.loadoutNamePlaceholder", { n: run.loadout_index + 1 });
  return `${ldName} · ${t(`simulate.fightProfile.${run.fight_profile_key}`)} · ${t(`simulate.rotation.${run.rotation}`)} · ${formatNumber(run.dps_mean, locale)} DPS`;
}
