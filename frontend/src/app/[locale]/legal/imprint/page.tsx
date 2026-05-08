import { getTranslations, setRequestLocale } from "next-intl/server";

import { Card } from "@/components/ui";
import type { Locale } from "@/i18n/config";

// Pull imprint fields from build-time env (NEXT_PUBLIC_*). Empty string =>
// render a placeholder so the missing field is visible at a glance.
function envOrPlaceholder(value: string | undefined, placeholder: string): string {
  const v = (value ?? "").trim();
  return v.length > 0 ? v : `[${placeholder}]`;
}

export default async function ImprintPage({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  const name = envOrPlaceholder(
    process.env.NEXT_PUBLIC_IMPRINT_NAME,
    t("legal.imprintFields.name"),
  );
  const street = envOrPlaceholder(
    process.env.NEXT_PUBLIC_IMPRINT_STREET,
    t("legal.imprintFields.street"),
  );
  const postalCity = envOrPlaceholder(
    process.env.NEXT_PUBLIC_IMPRINT_POSTAL_CITY,
    t("legal.imprintFields.postalCity"),
  );
  const country = envOrPlaceholder(
    process.env.NEXT_PUBLIC_IMPRINT_COUNTRY,
    t("legal.imprintFields.country"),
  );
  const email = envOrPlaceholder(
    process.env.NEXT_PUBLIC_IMPRINT_EMAIL,
    t("legal.imprintFields.email"),
  );
  const phoneRaw = (process.env.NEXT_PUBLIC_IMPRINT_PHONE ?? "").trim();

  return (
    <div className="container-page max-w-3xl">
      <Card>
        <h1 className="font-display text-3xl font-semibold text-accent">
          {t("legal.imprintTitle")}
        </h1>

        <h2 className="mt-6 text-lg font-semibold">{t("legal.imprintProviderHeading")}</h2>
        <address className="not-italic text-sm text-zinc-200">
          {name}
          <br />
          {street}
          <br />
          {postalCity}
          <br />
          {country}
        </address>

        <h2 className="mt-6 text-lg font-semibold">{t("legal.imprintContactHeading")}</h2>
        <p className="text-sm text-zinc-200">
          {t("legal.imprintFields.emailLabel")}: {email}
          {phoneRaw && (
            <>
              <br />
              {t("legal.imprintFields.phoneLabel")}: {phoneRaw}
            </>
          )}
        </p>

        <h2 className="mt-6 text-lg font-semibold">{t("legal.imprintResponsibleHeading")}</h2>
        <address className="not-italic text-sm text-zinc-200">
          {name}
          <br />
          {street}
          <br />
          {postalCity}
        </address>

        <h2 className="mt-6 text-lg font-semibold">{t("legal.imprintDisclaimerHeading")}</h2>
        <p className="whitespace-pre-line text-sm text-zinc-200">
          {t("legal.imprintDisclaimerBody")}
        </p>

        <h2 className="mt-6 text-lg font-semibold">{t("legal.imprintBlizzardHeading")}</h2>
        <p className="whitespace-pre-line text-sm text-zinc-200">
          {t("legal.imprintBlizzardBody")}
        </p>
      </Card>
    </div>
  );
}
