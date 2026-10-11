# RSS AI Project Manager — Cloudflare portal deployment

This Worker deploys the PM web interface and static assets to Cloudflare Workers. It is deliberately scoped to the portal document and static assets.

## Preserved architecture

- Portal HTML, JavaScript and assets: Cloudflare Workers static assets.
- /auth/*, /api/*, /health and other API endpoints: remain on the existing FastAPI/Docker backend through the existing Cloudflare Tunnel.
- PostgreSQL, email verification, RSS Core approval callback, PM account/session data and RAY execution remain on their existing backend services.
- Android APK compilation is a separate build job; Cloudflare Workers do not provide an Android SDK/Gradle build environment.

## Deployment

1. Create a Worker named rss-ai-project-manager-portal from this repository.
2. Set the Worker build/deploy configuration to use cloudflare-worker/wrangler.jsonc (working directory: repository root).
3. Ensure the Cloudflare zone is rssapps.cv and the account has permission to create Worker routes.
4. Deploy the Worker.
5. Verify the root page and static assets load from Workers, then verify https://pm.rssapps.cv/health still reaches FastAPI and returns the PM health response.
6. Verify login, registration, email verification, RSS Core approval callbacks, projects, tasks and conversations end to end.

## Route safety

Do not add a catch-all pm.rssapps.cv/* route to this static Worker. API routes must continue to reach FastAPI; a catch-all would intercept them and break authentication and workspace operations.

Production deployment has not been performed merely by adding these files. The Cloudflare account must deploy the Worker and confirm route behavior.
