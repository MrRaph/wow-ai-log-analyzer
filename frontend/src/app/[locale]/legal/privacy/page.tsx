import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card } from "@/components/ui";
import type { Locale } from "@/i18n/config";

const SECTIONS = [
  "controller",
  "scope",
  "dataCollected",
  "purposes",
  "legalBasis",
  "thirdParties",
  "wcl",
  "ai",
  "userApiKeys",
  "retention",
  "cookies",
  "rights",
  "complaint",
  "changes",
] as const;

export default async function PrivacyPage({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <div className="container-page max-w-3xl">
      <Card>
        <h1 className="font-display text-3xl font-semibold text-accent">
          {t("legal.privacyTitle")}
        </h1>
        <p className="mt-2 text-xs text-zinc-400">{t("legal.privacyLastUpdated")}</p>
        <p className="mt-4 whitespace-pre-line text-sm text-zinc-200">
          {t("legal.privacyIntro")}
        </p>

        {SECTIONS.map((key) => (
          <section key={key} className="mt-6">
            <h2 className="text-lg font-semibold">{t(`legal.privacySections.${key}.heading`)}</h2>
            <p className="mt-2 whitespace-pre-line text-sm text-zinc-200">
              {t(`legal.privacySections.${key}.body`)}
            </p>
          </section>
        ))}
      </Card>
    </div>
  );
}
