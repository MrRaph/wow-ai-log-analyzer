"use client";

import { Mail } from "lucide-react";
import { useTranslations } from "next-intl";
import { use, useState } from "react";

import { AuthShell } from "@/components/AuthShell";
import { TurnstileWidget, useTurnstileEnabled } from "@/components/TurnstileWidget";
import { Button, Card, FieldError, Input, Label } from "@/components/ui";
import { ApiClientError, apiFetch } from "@/lib/api";
import type { Locale } from "@/i18n/config";

export default function ForgotPasswordPage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = use(params);
  const t = useTranslations();
  const [email, setEmail] = useState("");
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [done, setDone] = useState(false);
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
      await apiFetch("/api/v1/auth/password-reset/request", {
        method: "POST",
        anonymous: true,
        locale,
        body: { email, captcha_token: captchaToken },
      });
      setDone(true);
    } catch (e) {
      setErr(e instanceof ApiClientError ? e.message : t("errors.generic"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell>
      <Card>
        <h1 className="mb-4 font-display text-2xl font-semibold">{t("auth.resetTitle")}</h1>
        {done ? (
          <p className="text-sm text-zinc-300">{t("auth.resetSent")}</p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <Label htmlFor="email">{t("auth.email")}</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                leftIcon={<Mail className="h-4 w-4" aria-hidden="true" />}
              />
            </div>
            <TurnstileWidget onToken={setCaptchaToken} />
            <FieldError>{err}</FieldError>
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? t("common.loading") : t("common.submit")}
            </Button>
          </form>
        )}
      </Card>
    </AuthShell>
  );
}
