# CI/CD Proof of Concept

## Purpose

This repository demonstrates a zero-subscription CI/CD path. GitHub-hosted runners
perform continuous integration, while a Windows laptop can be connected temporarily
as a self-hosted runner for an on-demand deployment. The laptop is not intended to be
a permanently available production server.

The proof demonstrates this path:

```text
push or pull request
  -> GitHub-hosted unit, contract, build and integration checks
  -> manual deploy approval on main
  -> temporary Windows self-hosted runner
  -> revision-tagged Docker Compose deployment
  -> health and smoke checks
  -> downloadable evidence artifact
```

## Existing continuous integration

- `.github/workflows/backend.yml` tests Decision, Planning and Participation, then
  runs the integrated HTTP and browser journeys against Docker Compose.
- `.github/workflows/frontend.yml` type-checks and builds the Vue application and
  runs its UI-focused browser tests.
- Both workflows run for pushes and pull requests on GitHub-hosted runners.

## Deployment assets

| File | Evidence provided |
| --- | --- |
| `.github/workflows/deploy-poc.yml` | Manual CD workflow and self-hosted runner selection |
| `compose.deploy.yaml` | Revision-tagged images, restart policy, labels and bounded logs |
| `.env.deploy.example` | Sanitized and repeatable configuration contract |
| `scripts/deploy.ps1` | Build, migration/startup, verification and evidence automation |
| `scripts/smoke-deployment.ps1` | Public endpoint and container-state verification |
| `scripts/rollback.ps1` | Rollback to the previously successful image set |
| `docs/DEPLOYMENT.md` | Operator setup, demonstration and recovery procedure |

## Security boundary

The self-hosted runner executes repository code on the laptop. It must be used only
with trusted branches and collaborators. The deployment workflow rejects branches
other than `main`, requires an explicit manual trigger, and reads the internal token
from a GitHub repository secret. Do not enable this runner for untrusted fork pull
requests. Stop `run.cmd` after collecting the demonstration evidence.

## Cost and scalability claims

The demonstration has no required service subscription. It uses GitHub-hosted CI
within the account's available Actions allowance and an existing laptop for CD.
Electricity, network access and the laptop remain real indirect costs.

Decision work is separated into API, recommendation/fact, research and preview
containers. Worker counts can be tuned through the environment, and additional
worker containers can be demonstrated with Docker Compose. The current proof does
not claim multi-host orchestration, automatic scaling or high availability.

The images use multi-stage or slim/distroless bases where appropriate, run application
processes as non-root users, and use bounded local log files. Rules-based semantics is
the default for the deployment proof so no paid model API or Ollama download is needed.

## Evidence checklist

Keep these items for the capstone submission:

- screenshot of the repository Actions page with CI jobs passing;
- screenshot of the temporary runner shown as online;
- successful `Deploy proof of concept` workflow run;
- uploaded `deployment-evidence-*` artifact;
- `compose-ps.txt`, `compose-images.txt`, and `smoke-results.json` from that artifact;
- screenshot of the running application and one completed journey;
- one successful rollback drill after at least two deployments;
- short explanation of the architecture, costs, limitations and security boundary.

The generated `.local-data/deploy/` records are intentionally ignored by Git. Commit
curated screenshots or reports only after checking that they contain no credentials.
