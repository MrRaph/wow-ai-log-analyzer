"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { clearAuth, getCachedUser, setCachedUser } from "@/lib/auth";
import { Button, Select } from "@/components/ui";
import type { Locale } from "@/i18n/config";
import { LOCALES } from "@/i18n/config";
import type { UserOut } from "@/types/api";

export function Header({ locale }: { locale: Locale }) {
  const t = useTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<UserOut | null>(null);

  useEffect(() => {
    let cancelled = false;
    const cached = getCachedUser();
    if (cached) setUser(cached);
    apiFetch<UserOut>("/api/v1/users/me")
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        setCachedUser(u);
      })
      .catch(() => {
        if (cancelled) return;
        setUser(null);
        clearAuth();
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  const switchLocale = (next: string) => {
    if (!LOCALES.includes(next as Locale)) return;
    const segments = pathname.split("/");
    if (segments.length > 1) segments[1] = next;
    router.push(segments.join("/") || `/${next}`);
  };

  const logout = () => {
    clearAuth();
    setUser(null);
    router.push(`/${locale}/login`);
  };

  return (
    <header className="sticky top-0 z-30 border-b border-bg-3 bg-bg-0/80 backdrop-blur">
      <div className="container-page flex items-center justify-between !py-4">
        <Link href={`/${locale}`} className="flex items-center gap-2 text-zinc-100 no-underline">
          <span className="font-display text-lg font-semibold tracking-wide text-accent">
            {t("app.name")}
          </span>
        </Link>
        <nav className="flex items-center gap-2">
          {user ? (
            <>
              <Link href={`/${locale}/analyze`} className="px-3 py-1.5 text-sm text-zinc-200 no-underline hover:text-accent">
                {t("nav.analyze")}
              </Link>
              <Link href={`/${locale}/top-logs`} className="px-3 py-1.5 text-sm text-zinc-200 no-underline hover:text-accent">
                {t("nav.topLogs")}
              </Link>
              {user.role === "admin" && (
                <Link href={`/${locale}/admin`} className="px-3 py-1.5 text-sm text-zinc-200 no-underline hover:text-accent">
                  {t("nav.admin")}
                </Link>
              )}
              <Link href={`/${locale}/profile`} className="px-3 py-1.5 text-sm text-zinc-200 no-underline hover:text-accent">
                {t("nav.profile")}
              </Link>
            </>
          ) : (
            <>
              <Link href={`/${locale}/login`} className="px-3 py-1.5 text-sm text-zinc-200 no-underline hover:text-accent">
                {t("nav.login")}
              </Link>
              <Link href={`/${locale}/register`} className="px-3 py-1.5 text-sm text-zinc-200 no-underline hover:text-accent">
                {t("nav.register")}
              </Link>
            </>
          )}
          <Select
            value={locale}
            onChange={(e) => switchLocale(e.target.value)}
            aria-label={t("common.language")}
            className="!w-28"
          >
            <option value="en">{t("common.english")}</option>
            <option value="de">{t("common.german")}</option>
          </Select>
          {user && (
            <Button variant="ghost" size="sm" onClick={logout}>
              {t("nav.logout")}
            </Button>
          )}
        </nav>
      </div>
    </header>
  );
}
