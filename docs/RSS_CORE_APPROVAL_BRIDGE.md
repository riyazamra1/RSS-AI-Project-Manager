# RSS AI Project Manager ↔ RSS Core approval bridge

Production environment variables:

- `RSS_CORE_APPROVAL_URL=https://rsscore.cv`
- `RSS_CORE_SERVICE_TOKEN=<private shared service token>`
- `APP_BASE_URL=<the deployed RSS AI Project Manager URL>`
- `RESEND_API_KEY=<Resend sending key>`
- `RESEND_FROM_EMAIL=Razeen Secure Solution <no-reply@rssapps.cv>`
- `RESEND_VERIFY_TEMPLATE_ID=d4a970b2-7756-4a8c-b418-fac4ef215618`
- `RESEND_APPROVAL_TEMPLATE_ID=752d16c6-2f2a-4d45-8ff2-40f5f876dc14`

The service token is server-to-server only. It must never be embedded in web JavaScript, Android builds, or API responses.

Flow:
1. PM creates a pending account.
2. PM sends email verification using the reusable Resend template.
3. Verified email causes PM to submit the approval request to RSS Core.
4. RSS Core stores the request and notifies the Core administrator.
5. Core Admin approves or rejects.
6. RSS Core calls PM's internal approval callback.
7. PM changes its own account state and sends the reusable approval template.
8. Only then can the PM credentials create a PM session.

PM credentials never authenticate against RSS Core.
