# Security

The Rivex team takes the security of the framework seriously. This document
explains how to report a vulnerability, what we do about it, and which
versions receive fixes.

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |

Only the latest minor release line receives security patches. Once 0.3.0 is
released, the 0.2.x line moves to "best effort" until 0.2.x's next patch
release, then is no longer supported.

## Reporting a vulnerability

**Please do not file a public issue.** Instead, report privately by email to
**<sengarsinghshreyansh@gmail.com>**. Include:

- A clear description of the issue and the impact you observed.
- Steps to reproduce — preferably a minimal `app.py` that triggers the bug.
- The Rivex version (`rivex --version`) and Python version (`python --version`).
- Whether you are willing to send a pull request.

We acknowledge new reports within **3 business days** and aim to ship a fix
within **30 days** for confirmed issues. Critical issues (RCE, auth bypass,
sensitive data exposure) are prioritised and may ship in a point release
sooner.

## Disclosure policy

- We follow **coordinated disclosure**. Please give us a reasonable window
  before publishing details.
- We credit reporters in the release notes unless they ask to remain
  anonymous.
- If a fix is non-trivial, we may ask for an embargo period of up to 90
  days while a CVE is reserved and a fix is prepared.

## What falls in scope

Anything that can be triggered by code that *uses* Rivex — e.g.

- A crafted request that bypasses middleware, dependency injection, or
  auth handlers.
- Unsafe default behaviour in `add_route`, `app.mount`, the static-file
  handler, or the request-body parser.
- Insecure defaults in `SecurityHeadersMiddleware`, `CSRFMiddleware`, or
  the session signer.
- Vulnerabilities in the bundled Rust core that surface to the Python
  wrapper (e.g. a buffer over-read in the JSON parser).

Bugs in *applications built with* Rivex are out of scope — those are
the application's responsibility, not the framework's.

## Hardening checklist for users

- Always pin a specific Rivex version in production (`rivex==0.2.0`, not
  `rivex>=0.2`).
- Run behind a reverse proxy (nginx, Caddy, Envoy) that terminates TLS.
   built-in server speaks plain HTTP for the worker processes.
- Set a strong `admin_token` if you enable the `rivex[admin]` dashboard,
  and put the dashboard behind a private network or VPN.
- Set `csrf=True` (the default) on `CSRFMiddleware` for any browser-facing
  surface that accepts cookies.
- Use `SecurityHeadersMiddleware` (the default) — it sets HSTS, X-Content-Type-Options,
  X-Frame-Options, Referrer-Policy, and a conservative Permissions-Policy.

## Receiving security updates

Watch the GitHub repository's **Releases** feed for new versions, and
subscribe to `pip install --upgrade rivex` in your CI. Security fixes land
in a patch release with the same minor line, and the changelog calls them
out under a "Security" section.
