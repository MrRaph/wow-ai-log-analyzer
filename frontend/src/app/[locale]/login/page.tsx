"use client";

import { Lock, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { use, useState } from "react";

import { AuthShell } from "@/components/AuthShell";
import { TurnstileWidget, useTurnstileEnabled } from "@/components/TurnstileWidget";
import { Button, Card, FieldError, Input, Label } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import type { Locale } from "@/i18n/config";
import type { TokenPair } from "@/types/api";

export default function LoginPage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  const t = useTranslations();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const captchaRequired = useTurnstileEnabled();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (captchaRequired === true && !captchaToken) {
      setErr(t("auth.captchaMissing"));
      return;
    }
    setErr(null);
    setLoading(true);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        anonymous: true,
        body: { email, password, captcha_token: captchaToken },
      });
      setTokens(tokens);
      router.push(`/${locale}/analyze`);
    } catch (e) {
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      <Card>
        <h1 className="mb-4 font-display text-2xl font-semibold">{t("auth.loginTitle")}</h1>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <Label htmlFor="email">{t("auth.email")}</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              leftIcon={<Mail className="h-4 w-4" aria-hidden="true" />}
            />
          </div>
          <div>
            <Label htmlFor="password">{t("auth.password")}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              leftIcon={<Lock className="h-4 w-4" aria-hidden="true" />}
            />
          </div>
          <TurnstileWidget onToken={setCaptchaToken} />
          <FieldError>{err}</FieldError>
          <Button type="submit" disabled={loading} className="w-full">
            {loading ? t("common.loading") : t("auth.loginTitle")}
          </Button>
        </form>
        <div className="mt-4 flex justify-between text-sm text-zinc-400">
          <Link href={`/${locale}/forgot-password`}>{t("auth.forgot")}</Link>
          <Link href={`/${locale}/register`}>{t("auth.noAccount")}</Link>
        </div>
      </Card>
    </AuthShell>
  );
}
