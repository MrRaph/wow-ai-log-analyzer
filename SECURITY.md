# Security policy

## Supported versions

This is a small self-hosted project — I patch security issues only on the
latest released `0.x` minor. If you're running an older version, the fix
will be to upgrade.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**
Instead, use GitHub's private vulnerability reporting:

→ <https://github.com/babatonga/wow-ai-log-analyzer/security/advisories/new>

Or email the maintainer at the address listed on the
[GitHub profile](https://github.com/babatonga).

What to include:

- A minimal reproduction. A small `curl` command or container run that
  shows the unintended behaviour is worth more than a long paragraph.
- The version / commit you tested against (a container tag like `0.3.0`
  is enough).
- Your suggested fix or mitigation, if you have one. Optional but
  speeds things up.

What you can expect:

- Acknowledgement within 7 days.
- A short triage note saying whether the report is in scope and, if so,
  a rough timeline.
- Credit in the fix's release notes if you'd like it.

## Out of scope

A few things that are unlikely to be accepted as security reports:

- Issues that require an already-compromised host (root on the Docker
  host, access to the Postgres data dir, etc.). The Docker socket mount
  for the optional admin "System" card is already documented as
  root-equivalent in `docker-compose.yml`.
- Missing security headers in self-hosted deployments — the reverse
  proxy in front of the container is the right place to set those.
- Theoretical attacks against the AI itself (jailbreaks, prompt
  injection from a WCL log). The AI's structured output is treated as
  untrusted; the analysis card sanitises it for rendering. If you've
  found an actual XSS in the rendered output, **that** is in scope.
