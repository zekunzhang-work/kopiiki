# Security Policy

Kopiiki is designed as a local developer tool. Do not expose the Flask backend directly to the public internet without adding authentication, rate limiting, request logging, and deployment-specific network controls.

## Supported Use

- Run the GUI locally on `http://localhost:5176`.
- Run the backend locally on `http://127.0.0.1:5002`.

## Default Protections

- The backend binds to `127.0.0.1` by default.
- CORS is restricted to local frontend origins by default.
- Extraction only accepts `http://` and `https://` target URLs.
- Localhost, private network, link-local, multicast, reserved, and unspecified IP targets are blocked by default to reduce SSRF risk.
- `.env` and `.env.*` are ignored by git.
- Design mode does not write source screenshots, source images, source videos, logo files, or commercial font files into the output ZIP.

## Sensitive Configuration

Store secrets in `.env` or environment variables:

```bash
GEMINI_API_KEY=...
```

Never commit real API keys. `GEMINI_API_KEY` is used only by the backend and is not returned by `/api/config`.

## Local Testing Overrides

To test against private or local targets:

```bash
KOPIIKI_ALLOW_PRIVATE_TARGETS=1
```

Use this only in trusted environments. It disables the default private-target block.

To adjust allowed browser origins:

```bash
KOPIIKI_ALLOWED_ORIGINS=http://localhost:5176,http://127.0.0.1:5176
```

To bind the backend to another interface:

```bash
KOPIIKI_HOST=127.0.0.1
```

## Reporting Vulnerabilities

Please do not open public issues for exploitable vulnerabilities. Contact the maintainer privately first, or open a minimal issue that says a security report is available without publishing exploit details.

Include:

- Affected version or commit.
- Reproduction steps.
- Expected impact.
- Any suggested mitigation.

## Release Checklist

Before publishing a release:

```bash
GEMINI_API_KEY= PYTHONPYCACHEPREFIX=/tmp/kopiiki-pycache backend/venv/bin/python -m unittest discover -s backend/tests
PYTHONPYCACHEPREFIX=/tmp/kopiiki-pycache backend/venv/bin/python -m compileall -q backend
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=moderate
```

If `GEMINI_API_KEY` is configured, also run the real Gemini smoke test and confirm the result manually.
