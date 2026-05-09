import { getRequestConfig } from "next-intl/server";
import { isLocale, getDefaultLocale } from "./config";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = isLocale(requested) ? requested : getDefaultLocale();
  const messages = (await import(`./messages/${locale}.json`)).default;
  return { locale, messages };
});
