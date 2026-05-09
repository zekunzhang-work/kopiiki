# Release Checklist

Use this checklist before tagging a public Kopiiki release.

## Code Health

- Working tree is clean.
- Backend unit tests pass.
- Backend compile check passes.
- Frontend lint passes.
- Frontend production build passes.
- `npm audit --audit-level=moderate` reports no vulnerabilities.

## Security

- `.env` and `.env.*` are not tracked by git.
- Backend binds to `127.0.0.1` by default for local runs.
- CORS is restricted to trusted local origins by default.
- Private network targets are blocked unless `KOPIIKI_ALLOW_PRIVATE_TARGETS=1`.
- `/api/config` does not expose API keys.

## Product

- Snapshot mode can generate a ZIP.
- Design mode without `GEMINI_API_KEY` returns a clear error.
- Design mode with Gemini can generate a ZIP.
- Design Capsule ZIP contains `DESIGN.md`, references, evidence JSON without image bytes, and validation script.
- Design Capsule ZIP does not include source screenshots, source images, source videos, logo files, or font files.
- History can download, copy paths, refresh, and delete archives.

## Documentation

- `README.md` is current.
- `README.zh-CN.md` is current.
- `frontend/README.md` is current.
- `SECURITY.md` is current.
- Legal boundary clearly distinguishes personal backup/research from unauthorized reuse or redistribution.
- Private launch notes, tweet drafts, screenshots, videos, and campaign materials are not tracked in git.

## Human TODO

These items cannot be completed from the codebase alone:

- Create a GitHub release for `v0.1.0-alpha`.
- Add repository topics in GitHub settings.
- Add a product screenshot or GIF to the GitHub README if desired.
- Record a short demo video if you want to announce on Twitter/X.
- Write the final Twitter/X post with the actual GitHub release link.
- Manually run a real Gemini smoke test with your own `GEMINI_API_KEY` before announcing Design mode broadly.

## Tagging

Recommended first public release label:

```text
v0.1.0-alpha
```

Use `v1.0.0` only after enough external testing confirms install reliability, extraction reliability, and Design Capsule quality across varied websites.
