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
      <section className="relative mb-10 overflow-hidden rounded-2xl border border-bg-3 bg-bg-1 p-8 sm:p-12">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-10 bg-[url('/brand/divider.png')] bg-cover bg-center opacity-40"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-r from-bg-1 via-bg-1/60 to-transparent"
        />
        <div className="flex flex-col items-center gap-8 sm:flex-row sm:justify-between">
          <div className="flex-1">
            <h1 className="font-display text-4xl font-semibold text-accent sm:text-5xl">
              {t("app.name")}
            </h1>
            <p className="mt-3 max-w-2xl text-lg text-zinc-300">{t("app.tagline")}</p>
          </div>
          <img
            src="/brand/hero-card.png"
            alt=""
            aria-hidden="true"
            className="h-48 w-48 shrink-0 drop-shadow-[0_0_28px_rgba(245,158,11,0.35)] sm:h-64 sm:w-64"
          />
        </div>
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
