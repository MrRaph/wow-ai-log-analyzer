import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { Providers } from "@/components/Providers";
import { Footer } from "@/components/Footer";
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
  const messages = await getMessages();

  return (
    <html lang={locale} className="dark">
      <body className="flex min-h-screen flex-col">
        <NextIntlClientProvider locale={locale as Locale} messages={messages}>
          <Providers>
            <WowheadScript locale={locale as Locale} />
            <Header locale={locale as Locale} />
            <main className="flex-1">{children}</main>
            <Footer locale={locale as Locale} />
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
