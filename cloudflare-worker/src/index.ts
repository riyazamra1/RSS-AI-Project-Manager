interface Env {
  ASSETS: Fetcher;
}

/**
 * Static web shell for RSS AI Project Manager.
 *
 * Route this Worker only to the portal document and static asset paths.
 * Do not attach a catch-all route: /auth/*, /api/* and /health must continue
 * to reach the existing FastAPI backend through its current Cloudflare Tunnel.
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    const isPortalAsset =
      path === "/" ||
      path === "/index.html" ||
      path === "/app.js" ||
      path.startsWith("/assets/") ||
      path.startsWith("/config/");

    if (!isPortalAsset) {
      return new Response("Not found", { status: 404 });
    }

    const response = await env.ASSETS.fetch(request);
    const headers = new Headers(response.headers);
    headers.set("X-Content-Type-Options", "nosniff");
    headers.set("X-Frame-Options", "DENY");
    headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
    headers.set("Cache-Control", path === "/" || path === "/index.html" || path === "/app.js" ? "no-cache" : "public, max-age=3600");
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  },
};
