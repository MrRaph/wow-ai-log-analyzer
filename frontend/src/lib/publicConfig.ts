"use client";
import { useQuery } from "@tanstack/react-query";

import type { PublicConfig } from "@/types/api";
import { apiFetch } from "./api";

/** Fetches /api/v1/config — instance-specific runtime values the frontend
 * needs (Turnstile site key, default locale, AI-enabled flag, etc.).
 *
 * Cached for 10 s + refetched on window focus so the analyze page sees
 * an admin's "AI provider = disabled" toggle within seconds, but bursts
 * of traffic don't hammer the backend.
 */
export function usePublicConfig() {
  return useQuery({
    queryKey: ["public-config"],
    queryFn: () => apiFetch<PublicConfig>("/api/v1/config", { anonymous: true }),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
  });
}
