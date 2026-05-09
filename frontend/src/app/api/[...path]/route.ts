// Catch-all route handler that forwards /api/* requests from this
// Next.js server to the FastAPI backend. Lives here (rather than as a
// next.config.ts ``rewrites`` rule) so the destination URL can be read
// from ``process.env.BACKEND_URL`` AT REQUEST TIME — the rewrites
// manifest bakes the destination at ``next build`` time, which would
// freeze whatever env happened to be set during the Docker image
// build (typically nothing) into the published artifact.
//
// Production deployment with an HTTPS reverse proxy in front never
// hits this handler — the proxy routes /api/* to the backend before
// it reaches Next.js. This handler is the fallback for direct
// http://localhost:3000 access and `npm run dev` outside docker.

import type { NextRequest } from "next/server";

// Force Node runtime — the Edge runtime can't reach a Docker DNS name
// like ``backend:8000`` and would lose access to ``process.env`` for
// non-NEXT_PUBLIC_* keys at runtime.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Headers we strip before forwarding upstream. Three groups:
//
//   1. ``host`` — points at this Next.js server, not the backend.
//   2. Hop-by-hop headers (RFC 7230 §6.1) that don't make sense to
//      forward; ``content-length`` is recomputed by fetch.
//   3. ``x-forwarded-*`` / ``forwarded`` — security-critical. The
//      backend's rate limiter trusts these headers to identify the
//      real client IP. We can't trust whatever the client sent (they
//      could spoof "1.2.3.4" to hop the per-IP limits), and we don't
//      have a reliable way to obtain the real socket peer in a
//      Next.js route handler. Stripping them lets the rate limiter
//      fall back to ``request.client`` (the frontend container IP) —
//      coarser, but not spoofable. In production with Caddy/nginx
//      in front the proxy intercepts /api/* before this handler
//      runs, so the proxy's correctly-set XFF reaches the backend.
const HOP_BY_HOP_REQUEST_HEADERS = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-length",
  "x-forwarded-for",
  "x-forwarded-host",
  "x-forwarded-proto",
  "x-forwarded-port",
  "x-real-ip",
  "forwarded",
]);

const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function backendUrl(): string {
  // Read at request time so docker-compose can inject the inter-
  // container DNS name (BACKEND_URL=http://backend:8000) without
  // requiring a frontend rebuild.
  return process.env.BACKEND_URL ?? "http://localhost:8000";
}

async function proxy(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await ctx.params;
  const target = new URL(
    `${backendUrl().replace(/\/$/, "")}/api/${path.join("/")}`,
  );
  target.search = req.nextUrl.search;

  const fwdHeaders = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_REQUEST_HEADERS.has(key.toLowerCase())) {
      fwdHeaders.set(key, value);
    }
  });

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers: fwdHeaders,
    redirect: "manual",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = req.body;
    // Required by undici when sending a streaming body.
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), init);
  } catch (err) {
    // Backend unreachable — surface a clean 502 so the frontend's
    // error toast says something useful instead of "Internal Server
    // Error".
    console.error("[api-proxy] upstream fetch failed:", target.toString(), err);
    return new Response(
      JSON.stringify({
        error: {
          code: "upstream_unreachable",
          message: "Backend unreachable.",
          details: { url: target.toString() },
        },
      }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  const respHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_RESPONSE_HEADERS.has(key.toLowerCase())) {
      respHeaders.set(key, value);
    }
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: respHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as OPTIONS,
  proxy as HEAD,
};
