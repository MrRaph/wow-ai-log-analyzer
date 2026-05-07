"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { use, useState } from "react";

import { Button, Card, FieldError, Input, Label } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type { Locale } from "@/i18n/config";

export default function AcceptInvitePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  const t = useTranslations();
  const router = useRouter();
  const search = useSearchParams();
  const token = search.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (password.length < 8) {
      setErr(t("auth.passwordsTooShort"));
      return;
    }
    setLoading(true);
    try {
      await apiFetch("/api/v1/auth/accept-invite", {
        method: "POST",
        anonymous: true,
        body: { token, password, display_name: displayName },
      });
      router.push(`/${locale}/login`);
    } catch (e) {
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container-page mx-auto max-w-md">
      <Card>
        <h1 className="mb-4 font-display text-2xl font-semibold">{t("auth.acceptInviteTitle")}</h1>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <Label htmlFor="display_name">{t("auth.displayName")}</Label>
            <Input
              id="display_name"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="password">{t("auth.newPassword")}</Label>
            <Input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <FieldError>{err}</FieldError>
          <Button type="submit" disabled={loading || !token} className="w-full">
            {loading ? t("common.loading") : t("auth.acceptInviteSubmit")}
          </Button>
        </form>
      </Card>
    </div>
  );
}
