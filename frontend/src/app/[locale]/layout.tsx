import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { Providers } from "@/components/Providers";
import { Header } from "@/components/Header";
import { WowheadScript } from "@/components/WowheadScript";
import { LOCALES, type Locale, isLocale } from "@/i18n/config";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  setRequestLocale(locale);
  const [messages, t] = await Promise.all([getMessages(), getTranslations()]);

  return (
    <html lang={locale} className="dark">
      <body>
        <NextIntlClientProvider locale={locale as Locale} messages={messages}>
          <Providers>
            <WowheadScript locale={locale as Locale} />
            <Header locale={locale as Locale} />
            <main>{children}</main>
            <footer className="container-page text-xs text-zinc-500">
              <p>{t("app.footer")}</p>
            </footer>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
