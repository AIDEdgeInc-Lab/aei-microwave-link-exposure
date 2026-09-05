# Publishing process

**This repository is public (`AIDEdgeInc-Lab/aei-microwave-link-exposure`).**
This document describes the process, mirrored from `aei-3gpp-kpi-validator`'s
and `aei-geo-features`' publishing setup.

## How a release would be published

- **Normal path**: a maintainer publishes a GitHub Release. This fires
  the workflow's `release: published` trigger, which builds the wheel/
  sdist and publishes them to production PyPI (`environment: pypi`).
- **Manual path**: the workflow can also be run manually via
  `workflow_dispatch` with a `target` input of `testpypi` (default) or
  `pypi`. A manual run always requires `target` to be chosen explicitly;
  `pypi` is never the default.

Both paths run through the same `build` job first, and both publish
jobs are mutually exclusive - only one of `publish-testpypi` /
`publish-pypi` ever runs for a given trigger.

## Why Trusted Publishing instead of a token

PyPI Trusted Publishing lets a specific GitHub Actions workflow
(identified by repo, workflow filename, and environment) request a
short-lived upload credential directly from PyPI via OpenID Connect (OIDC)
at publish time. There is no long-lived `PYPI_API_TOKEN` secret to create,
rotate, store in GitHub Secrets, or accidentally leak in a log.

## Trusted Publisher registration

Must be registered as a Trusted Publisher on both pypi.org and
test.pypi.org, tied to this repository, the `publish.yml` workflow
filename, and the `pypi`/`testpypi` environments respectively. That
registration happens on PyPI's own site (Account Settings -> Publishing),
not in this repository - there is nothing to configure here beyond the
workflow file itself, and it must be done by a human with access to the
relevant PyPI account. The `pypi` GitHub Environment additionally has a
required reviewer configured with admin-bypass disabled, so a production
deployment always pauses for manual approval in the Actions UI regardless
of what triggered it.

## Current state

- **The GitHub repository is public** (`AIDEdgeInc-Lab/aei-microwave-link-exposure`).
- The `pypi` GitHub Environment requires manual reviewer approval before
  any deployment to it proceeds; `testpypi` does not.
- `.github/workflows/publish.yml` triggers on a published GitHub Release
  (routes to the `pypi` job only) or manual `workflow_dispatch` (routes to
  either `testpypi` or `pypi`, `testpypi` by default). It has no
  `push`/`pull_request` trigger.
- `ci.yml` runs on push/PR against this repository and validates the
  test suite; it does not publish anywhere.
- **Trusted Publisher relationships are NOT yet registered** on pypi.org
  or test.pypi.org for this repository. Until that one-time manual
  registration is done, both publish jobs will fail authentication -
  this is expected and intentional at this stage.
- **No version has been published** to either index yet. Check
  https://pypi.org/project/aei-microwave-link-exposure/ and
  https://test.pypi.org/project/aei-microwave-link-exposure/ directly for
  the current state rather than trusting this file to stay up to date as
  future releases ship.
