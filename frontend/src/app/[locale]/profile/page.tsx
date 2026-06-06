"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, use, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { Button, Card, FieldError, Input, Label, Select } from "@/components/ui";
import { UserAiConfigPanel } from "@/components/UserAiConfigPanel";
import { WclConnectionPanel } from "@/components/WclConnectionPanel";
import { ApiClientError, apiFetch } from "@/lib/api";
import { setCachedUser, clearAuth } from "@/lib/auth";
import type { Locale } from "@/i18n/config";
import type { UserOut } from "@/types/api";

export default function ProfilePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  return <AuthGuard locale={locale}>{(user) => <ProfileView locale={locale} user={user} />}</AuthGuard>;
}

function ProfileView({ user, locale }: { user: UserOut; locale: Locale }) {
  const t = useTranslations();
  const router = useRouter();
  const [displayName, setDisplayName] = useState(user.display_name);
  const [chosenLocale, setChosenLocale] = useState(user.locale || locale);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const saveMut = useMutation({
    mutationFn: () =>
      apiFetch<UserOut>("/api/v1/users/me", {
        method: "PATCH",
        body: {
          display_name: displayName,
          locale: chosenLocale,
          current_password: currentPassword || undefined,
          new_password: newPassword || undefined,
        },
      }),
    onSuccess: (u) => {
      setCachedUser(u);
      setOk(true);
      setErr(null);
      setCurrentPassword("");
      setNewPassword("");
    },
    onError: (e) => {
      setOk(false);
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  const deleteAccountMut = useMutation({
    mutationFn: () => apiFetch("/api/v1/users/me", { method: "DELETE" }),
    onSuccess: () => {
      clearAuth();
      router.replace(`/${locale}`);
    },
    onError: (e) => {
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic"));
    },
  });

  return (
    <div className="container-page mx-auto max-w-xl space-y-4">
      <h1 className="font-display text-3xl font-semibold">{t("profile.title")}</h1>
      <Card>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            saveMut.mutate();
          }}
        >
          <div>
            <Label>{t("auth.email")}</Label>
            <Input value={user.email} disabled />
          </div>
          <div>
            <Label>{t("auth.displayName")}</Label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
          </div>
          <div>
            <Label>{t("profile.language")}</Label>
            <Select value={chosenLocale} onChange={(e) => setChosenLocale(e.target.value)}>
              <option value="en">{t("common.english")}</option>
              <option value="de">{t("common.german")}</option>
              <option value="fr">{t("common.french")}</option>
            </Select>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <Label>{t("auth.currentPassword")}</Label>
              <Input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div>
              <Label>{t("auth.newPassword")}</Label>
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
              />
            </div>
          </div>
          <FieldError>{err}</FieldError>
          {ok && <p className="text-sm text-emerald-400">{t("admin.saved")}</p>}
          <Button type="submit" disabled={saveMut.isPending}>
            {t("common.save")}
          </Button>
        </form>
      </Card>
      <Suspense fallback={null}>
        <div className="space-y-4">
          <WclConnectionPanel locale={locale} flavor="retail" />
          <WclConnectionPanel locale={locale} flavor="fresh" />
        </div>
      </Suspense>
      <UserAiConfigPanel />
      <Card className="border-red-500/30">
        <h2 className="mb-1 font-semibold text-red-300">
          {t("profile.deleteAccountHeading")}
        </h2>
        <p className="mb-3 text-sm text-zinc-400">
          {t("profile.deleteAccountWarning")}
        </p>
        <Button
          variant="danger"
          onClick={() => {
            if (window.confirm(t("profile.deleteAccountConfirm"))) {
              deleteAccountMut.mutate();
            }
          }}
          disabled={deleteAccountMut.isPending}
        >
          {deleteAccountMut.isPending
            ? t("common.loading")
            : t("profile.deleteAccountButton")}
        </Button>
      </Card>
    </div>
  );
}
