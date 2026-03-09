# Auth

## Preferred Agent Auth

For agent callers, use the configured bearer token path for the target deployment.

- Header: `Authorization: Bearer {{BEARER_TOKEN}}`
- Public OpenAPI URL: `{{OPENAPI_URL}}`
- Public API prefix: `{{API_PREFIX}}`

Do not embed real deployment secrets, admin credentials, or internal runner tokens in a shared skill.

## Quick Verification

Use the current token against a low-risk authenticated endpoint, such as:

- `GET /trade-calendar/latest-trade-date`
- `GET /stocks/basic?page=1&page_size=1`

If auth fails, stop before attempting deeper workflows.
