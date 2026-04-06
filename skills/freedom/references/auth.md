# Auth

## Preferred Agent Auth

For OpenClaw or other automation, use a bearer token from `personal-authenticator`.

- Header: `Authorization: Bearer {{BEARER_TOKEN}}`
- Public OpenAPI URL: `https://www.jamesgu.cn/freedom/api/openapi.json`
- Public API prefix: `https://www.jamesgu.cn/freedom/api`

Valid bearer tokens are:

- a `personal-authenticator` access token
- a `personal-authenticator` API Key owned by `james`

Do not embed real deployment secrets, admin credentials, or internal runner tokens in a shared skill.

## Quick Verification

Use the current token against a low-risk authenticated endpoint, such as:

- `GET /auth/me`
- `GET /trade-calendar/latest-trade-date`
- `GET /stocks/basic?page=1&page_size=1`

If auth fails, stop before attempting deeper workflows.
