"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { use, useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { Button, Card, Input, Label, Select } from "@/components/ui";
import { TopLogsToolsCard } from "@/components/admin/TopLogsToolsCard";
import { WowDataCard } from "@/components/admin/WowDataCard";
import { ApiClientError, apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Locale } from "@/i18n/config";
import type { AdminSettings, Invite, UserOut } from "@/types/api";

export default function AdminPage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  return (
    <AuthGuard locale={locale} requireAdmin>
      {(currentUser) => <AdminView locale={locale} currentUserId={currentUser.id} />}
    </AuthGuard>
  );
}

function AdminView({ locale, currentUserId }: { locale: Locale; currentUserId: string }) {
  const t = useTranslations();
  const qc = useQueryClient();

  const settingsQ = useQuery({
    queryKey: ["admin-settings"],
    queryFn: () => apiFetch<AdminSettings>("/api/v1/admin/settings"),
  });
  const usersQ = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<UserOut[]>("/api/v1/admin/users"),
  });
  const invitesQ = useQuery({
    queryKey: ["admin-invites"],
    queryFn: () => apiFetch<Invite[]>("/api/v1/admin/invites"),
  });

  const [allowReg, setAllowReg] = useState<boolean>(false);
  const [provider, setProvider] = useState<string>("anthropic");
  const [model, setModel] = useState<string>("claude-sonnet-4-6");

  useEffect(() => {
    if (settingsQ.data) {
      setAllowReg(settingsQ.data.allow_registration);
      setProvider(settingsQ.data.ai_provider);
      setModel(settingsQ.data.ai_model);
    }
  }, [settingsQ.data]);

  const saveSettings = useMutation({
    mutationFn: () =>
      apiFetch<AdminSettings>("/api/v1/admin/settings", {
        method: "PATCH",
        body: { allow_registration: allowReg, ai_provider: provider, ai_model: model },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-settings"] }),
  });

  const [inviteEmail, setInviteEmail] = useState("");
  const inviteMut = useMutation({
    mutationFn: () =>
      apiFetch<Invite>("/api/v1/admin/invites", {
        method: "POST",
        body: { email: inviteEmail, locale },
      }),
    onSuccess: () => {
      setInviteEmail("");
      qc.invalidateQueries({ queryKey: ["admin-invites"] });
    },
  });

  const revokeMut = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/admin/invites/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invites"] }),
  });

  const updateUserMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      apiFetch<UserOut>(`/api/v1/admin/users/${id}`, { method: "PATCH", body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const deleteUserMut = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/admin/users/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (e) => {
      window.alert(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  return (
    <div className="container-page space-y-6">
      <header>
        <h1 className="font-display text-3xl font-semibold">{t("admin.title")}</h1>
      </header>

      <Card>
        <h2 className="mb-3 text-lg font-semibold">{t("admin.settings")}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-3 flex items-center gap-3">
            <input
              id="allowReg"
              type="checkbox"
              checked={allowReg}
              onChange={(e) => setAllowReg(e.target.checked)}
              className="h-4 w-4 accent-amber-500"
            />
            <label htmlFor="allowReg" className="text-sm">
              {t("admin.allowRegistration")}
            </label>
          </div>
          <div>
            <Label>{t("admin.aiProvider")}</Label>
            <Select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="anthropic">Anthropic Claude</option>
              <option value="openai">OpenAI</option>
              <option value="local">Local (llama.cpp)</option>
            </Select>
          </div>
          <div>
            <Label>{t("admin.aiModel")}</Label>
            {provider === "local" ? (
              <input
                value={model}
                disabled
                className="w-full rounded-md border border-bg-3 bg-bg-2 px-3 py-2 text-sm text-zinc-400"
              />
            ) : (
              <Select value={model} onChange={(e) => setModel(e.target.value)}>
                {provider === "anthropic" && (
                  <>
                    <option value="claude-sonnet-4-6">claude-sonnet-4-6</option>
                    <option value="claude-opus-4-7">claude-opus-4-7</option>
                    <option value="claude-haiku-4-5-20251001">claude-haiku-4-5</option>
                  </>
                )}
                {provider === "openai" && (
                  <>
                    <option value="gpt-4o">gpt-4o</option>
                    <option value="gpt-4o-mini">gpt-4o-mini</option>
                    <option value="o1-preview">o1-preview</option>
                  </>
                )}
              </Select>
            )}
            {provider === "local" && (
              <p className="mt-1 text-xs text-zinc-500">
                {locale === "de"
                  ? "Modell ist durch LOCAL_AI_MODEL in der .env festgelegt. Zum Wechseln den local-ai Container mit dem neuen Modell neu starten."
                  : "Model is set by LOCAL_AI_MODEL in .env. To switch, restart the local-ai container with the new value."}
              </p>
            )}
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={() => saveSettings.mutate()} disabled={saveSettings.isPending}>
            {t("common.save")}
          </Button>
          {saveSettings.isSuccess && <span className="text-xs text-emerald-400">{t("admin.saved")}</span>}
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 text-lg font-semibold">{t("admin.invites")}</h2>
        <form
          className="flex flex-col gap-3 md:flex-row md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            if (inviteEmail) inviteMut.mutate();
          }}
        >
          <div className="md:flex-1">
            <Label>{t("admin.newInviteEmail")}</Label>
            <Input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={inviteMut.isPending}>
            {inviteMut.isPending ? t("common.loading") : t("admin.sendInvite")}
          </Button>
        </form>
        <table className="mt-4 w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-zinc-400">
            <tr>
              <th className="px-2 py-2 text-left">{t("auth.email")}</th>
              <th className="px-2 py-2 text-left">{t("admin.createdAt")}</th>
              <th className="px-2 py-2 text-left">{t("admin.expiresAt")}</th>
              <th className="px-2 py-2 text-left">{t("admin.accepted")}</th>
              <th className="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(invitesQ.data ?? []).map((inv) => (
              <tr key={inv.id} className="border-t border-bg-3">
                <td className="px-2 py-2">{inv.email}</td>
                <td className="px-2 py-2">{formatDateTime(inv.created_at, locale)}</td>
                <td className="px-2 py-2">{formatDateTime(inv.expires_at, locale)}</td>
                <td className="px-2 py-2">
                  {inv.revoked
                    ? "✗"
                    : inv.accepted_at
                      ? formatDateTime(inv.accepted_at, locale)
                      : "—"}
                </td>
                <td className="px-2 py-2 text-right">
                  {!inv.accepted_at && !inv.revoked && (
                    <Button size="sm" variant="ghost" onClick={() => revokeMut.mutate(inv.id)}>
                      {t("admin.revoke")}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <WowDataCard locale={locale} />
      <TopLogsToolsCard locale={locale} />

      <Card className="!p-0 overflow-hidden">
        <div className="px-5 pt-5">
          <h2 className="mb-3 text-lg font-semibold">{t("admin.users")}</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-xs uppercase tracking-wide text-zinc-400">
              <tr>
                <th className="px-3 py-2 text-left">{t("auth.email")}</th>
                <th className="px-3 py-2 text-left">{t("auth.displayName")}</th>
                <th className="px-3 py-2 text-left">{t("admin.role")}</th>
                <th className="px-3 py-2 text-left">{t("admin.active")}</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {(usersQ.data ?? []).map((u) => {
                const isSelf = u.id === currentUserId;
                const isDeleting =
                  deleteUserMut.isPending && deleteUserMut.variables === u.id;
                return (
                  <tr key={u.id} className="border-t border-bg-3">
                    <td className="px-3 py-2">{u.email}</td>
                    <td className="px-3 py-2">{u.display_name}</td>
                    <td className="px-3 py-2">
                      <Select
                        value={u.role}
                        onChange={(e) =>
                          updateUserMut.mutate({ id: u.id, payload: { role: e.target.value } })
                        }
                        className="!w-32"
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                      </Select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={u.is_active}
                        onChange={(e) =>
                          updateUserMut.mutate({
                            id: u.id,
                            payload: { is_active: e.target.checked },
                          })
                        }
                        className="h-4 w-4 accent-amber-500"
                      />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={isSelf || isDeleting}
                        title={
                          isSelf
                            ? t("admin.deleteUserSelfHint")
                            : t("admin.deleteUserButton")
                        }
                        aria-label={t("admin.deleteUserButton")}
                        onClick={() => {
                          if (
                            window.confirm(
                              t("admin.deleteUserConfirm", { email: u.email }),
                            )
                          ) {
                            deleteUserMut.mutate(u.id);
                          }
                        }}
                      >
                        {isDeleting ? "…" : <Trash2 className="h-4 w-4" aria-hidden="true" />}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
