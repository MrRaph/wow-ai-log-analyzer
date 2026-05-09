import createMiddleware from "next-intl/middleware";
import { LOCALES, getDefaultLocale } from "./i18n/config";

// Middleware module is loaded once at server start, so reading
// ``getDefaultLocale()`` here picks up the container's runtime
// ``DEFAULT_LOCALE`` env value (not the build-time one).
export default createMiddleware({
  locales: LOCALES,
  defaultLocale: getDefaultLocale(),
  localePrefix: "always",
});

export const config = {
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
