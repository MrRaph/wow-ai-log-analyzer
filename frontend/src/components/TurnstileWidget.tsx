"use client";

import { useEffect, useId, useRef } from "react";

// Build-time config: empty string disables the widget completely (the
// component renders nothing). Set NEXT_PUBLIC_TURNSTILE_SITE_KEY in .env
// to opt in. The matching backend env var is TURNSTILE_ENABLED+TURNSTILE_SECRET_KEY.
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";
export const isTurnstileEnabled = TURNSTILE_SITE_KEY.length > 0;

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

  useEffect(() => {
    if (!isTurnstileEnabled) return;
    if (!containerRef.current) return;
    let cancelled = false;
    loadTurnstileScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.turnstile) return;
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: TURNSTILE_SITE_KEY,
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
  }, []);

  if (!isTurnstileEnabled) return null;
  return <div id={`turnstile-${id}`} ref={containerRef} className="mt-1" />;
}
