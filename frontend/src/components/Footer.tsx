import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/config";

// Site-wide footer rendered on every page (also pre-login). Links to the
// legally required Impressum (TMG/DDG) and Datenschutzerklärung (DSGVO/GDPR)
// stay reachable without authentication, matching German legal requirements
// for commercial-style web services.
export async function Footer({ locale }: { locale: Locale }) {
  const t = await getTranslations();
  const year = new Date().getFullYear();
  return (
    <footer className="mt-12 border-t border-bg-3 bg-bg-1/40">
      <div className="container-page flex flex-col items-center justify-between gap-3 !py-6 text-xs text-zinc-500 sm:flex-row sm:gap-4">
        <p className="text-center sm:text-left">
          © {year} · {t("app.footer")}
        </p>
        <nav className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
          <Link
            href={`/${locale}/legal/imprint`}
            className="text-zinc-400 no-underline hover:text-accent"
          >
            {t("legal.imprintLink")}
          </Link>
          <Link
            href={`/${locale}/legal/privacy`}
            className="text-zinc-400 no-underline hover:text-accent"
          >
            {t("legal.privacyLink")}
          </Link>
        </nav>
      </div>
    </footer>
  );
}
