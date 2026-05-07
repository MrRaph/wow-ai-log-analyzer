import Link from "next/link";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card } from "@/components/ui";
import type { Locale } from "@/i18n/config";

export default async function Home({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  return (
    <div className="container-page">
      <section className="mb-10">
        <h1 className="font-display text-4xl font-semibold text-accent">{t("app.name")}</h1>
        <p className="mt-2 max-w-2xl text-lg text-zinc-300">{t("app.tagline")}</p>
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="text-lg font-semibold">{t("nav.analyze")}</h2>
          <p className="mt-2 text-sm text-zinc-400">{t("analyze.subtitle")}</p>
          <Link
            href={`/${locale}/analyze`}
            className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-fg no-underline hover:bg-accent-muted"
          >
            {t("nav.analyze")}
          </Link>
        </Card>
        <Card>
          <h2 className="text-lg font-semibold">{t("nav.topLogs")}</h2>
          <p className="mt-2 text-sm text-zinc-400">
            {locale === "de"
              ? "Browse die Top-DPS- und Top-HPS-Logs der aktuellen Patches pro Klasse, Spec und Boss."
              : "Browse the current patch's top DPS and HPS logs per class, spec and encounter."}
          </p>
          <Link
            href={`/${locale}/top-logs`}
            className="mt-4 inline-block rounded-md bg-bg-3 px-4 py-2 text-sm font-semibold text-zinc-100 no-underline hover:bg-bg-2"
          >
            {t("nav.topLogs")}
          </Link>
        </Card>
      </div>
    </div>
  );
}
