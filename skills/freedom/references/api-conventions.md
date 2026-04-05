# API Conventions

These are the response and input rules that matter in practice.

## Symbol Format

- Preferred code format is `ts_code`, for example `000001.SZ`.
- Some endpoints may accept raw numeric codes, but normalize to `ts_code` before chaining requests.

## Date Format

- Accept user input in `YYYYMMDD` or `YYYY-MM-DD`.
- Expect many market responses to use `YYYYMMDD`.

## Auth Model

- Browser login is proxied to `personal-authenticator`.
- Protected API verification is delegated to `personal-authenticator`.
- OpenClaw should use an existing bearer token, usually a `james`-owned API Key.

## Response Shape

Common paginated structure:

```json
{
  "code": 200,
  "data": [],
  "total": 0,
  "page": 1,
  "page_size": 200
}
```

## Empty Data

- `code=200` with `data=[]` is often a valid no-data result.
- Do not treat every empty dataset as an API error.

## Query Strategy

- Resolve the latest trade date before "today" style market questions.
- Prefer high-frequency endpoints first, then enrich with financial or event detail.
- Avoid calling many low-signal endpoints when one screening endpoint can answer the question.
