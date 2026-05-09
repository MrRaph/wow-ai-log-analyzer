"use client";

import { useEffect, useId, useRef } from "react";

import { usePublicConfig } from "@/lib/publicConfig";

/** Hook: ``true`` iff the backend has Turnstile enabled AND has handed
 * us a non-empty site key via /api/v1/config. Pages use this to gate
 * their submit handlers ("require captcha token before allowing form
 * submit"). Returns ``undefined`` while the config is still loading,
 * which callers treat as "don't submit yet".
 */
export function useTurnstileEnabled(): boolean | undefined {
  const cfg = usePublicConfig();
  if (cfg.data == null) return undefined;
  return cfg.data.captcha_enabled && cfg.data.turnstile_site_key.length > 0;
}

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement | string,
        opts: {
          sitekey: string;
          callback?: (token: string) => void;
          "error-callback"?: () => void;
          "expired-callback"?: () => void;
          theme?: "light" | "dark" | "auto";
        },
      ) => string;
      reset: (widgetId?: string) => void;
      remove: (widgetId?: string) => void;
    };
    onloadTurnstileCallback?: () => void;
  }
}

const SCRIPT_SRC =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let scriptLoaded = false;
let scriptLoadingPromise: Promise<void> | null = null;

function loadTurnstileScript(): Promise<void> {
  if (scriptLoaded) return Promise.resolve();
  if (scriptLoadingPromise) return scriptLoadingPromise;
  scriptLoadingPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src^="https://challenges.cloudflare.com/turnstile/v0/"]`,
    );
    if (existing) {
      // Either already loaded by a previous mount or in flight; wait for it.
      if (window.turnstile) {
        scriptLoaded = true;
        resolve();
        return;
      }
      existing.addEventListener("load", () => {
        scriptLoaded = true;
        resolve();
      });
      existing.addEventListener("error", () => reject(new Error("turnstile load failed")));
      return;
    }
    const s = document.createElement("script");
    s.src = SCRIPT_SRC;
    s.async = true;
    s.defer = true;
    s.onload = () => {
      scriptLoaded = true;
      resolve();
    };
    s.onerror = () => reject(new Error("turnstile load failed"));
    document.head.appendChild(s);
  });
  return scriptLoadingPromise;
}

interface Props {
  /** Called whenever Cloudflare hands us a fresh token (or null on reset/expire). */
  onToken: (token: string | null) => void;
}

export function TurnstileWidget({ onToken }: Props) {
  const id = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);
  const cfg = usePublicConfig();
  const siteKey = cfg.data?.turnstile_site_key ?? "";
  const enabled = !!cfg.data?.captcha_enabled && siteKey.length > 0;

  useEffect(() => {
    if (!enabled) return;
    if (!containerRef.current) return;
    let cancelled = false;
    loadTurnstileScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.turnstile) return;
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          theme: "dark",
          callback: (token: string) => onToken(token),
          "error-callback": () => onToken(null),
          "expired-callback": () => onToken(null),
        });
      })
      .catch(() => {
        // Network blocked / Cloudflare unreachable — pass null so caller can
        // surface a clear error instead of silently submitting without token.
        onToken(null);
      });
    return () => {
      cancelled = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
    // intentionally exclude onToken: re-rendering the widget on every parent
    // render would loop. The latest onToken closure is captured at mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, siteKey]);

  if (!enabled) return null;
  return <div id={`turnstile-${id}`} ref={containerRef} className="mt-1" />;
}
