# CI/CD Demonstration Evidence

This evidence pack records a successful, on-demand CI/CD demonstration performed
on 24-25 October 2026. It complements the implementation in
[`CI_CD.md`](CI_CD.md) and the operating procedure in
[`DEPLOYMENT.md`](DEPLOYMENT.md).

The deployment was intentionally performed with a temporary Windows self-hosted
runner. GitHub-hosted runners continue to run continuous integration; the laptop
is only needed while a manually approved deployment is running.

## What Was Demonstrated

```text
Pull request and automated checks
  -> GitHub Actions secret available to the deployment workflow
  -> temporary, labelled self-hosted runner connected
  -> manual deployment job received by that runner
  -> Docker Compose build, deployment, health checks and smoke checks
  -> deployment artifact retained by GitHub Actions
  -> deployed application reachable locally
```

## Evidence Index

| # | Evidence | What it demonstrates |
| --- | --- | --- |
| 1 | [Pull-request change set](evidence/ci-cd/01-pull-request-cicd-files.png) | The deployment workflow, deployment Compose overlay, environment template and PowerShell automation were reviewed as repository changes. |
| 2 | [Passing CI checks](evidence/ci-cd/02-ci-checks-passed.png) | The pull request shows 12 successful checks, including Decision, Planning, Participation, integration and frontend jobs. This is the continuous-integration gate before deployment. |
| 3 | [Actions secret configured](evidence/ci-cd/03-actions-secret-configured.png) | `INTERNAL_API_TOKEN` exists as a repository Actions secret. GitHub hides its value; it is injected into the deployment workflow rather than committed. |
| 4 | [Local deployment build](evidence/ci-cd/04-local-deployment-build.png) | The reusable deployment script builds the Docker images and tags the deployment with a Git revision. |
| 5 | [Local smoke checks](evidence/ci-cd/05-local-smoke-checks-passed.png) | Frontend, Planning and Participation health endpoints all passed after deployment. |
| 6 | [Local container status](evidence/ci-cd/06-local-container-status.png) | The local Docker Compose deployment has healthy API, worker, frontend and PostgreSQL containers, with revision-tagged application images. |
| 7 | [Local evidence generated](evidence/ci-cd/07-local-evidence-generated.png) | The deployment script reports its evidence output location after a successful run. |
| 8 | [Runner registration and listening state](evidence/ci-cd/08-runner-registered-listening.png) | The temporary Windows runner was registered with the `what2do-deploy` label and connected to GitHub without being installed as a permanent service. |
| 9 | [Runner idle](evidence/ci-cd/09-runner-idle.jpg) | GitHub recognised the temporary runner and its `self-hosted`, `Windows`, `X64` and `what2do-deploy` labels before dispatch. |
| 10 | [Runner active](evidence/ci-cd/10-runner-active.jpg) | GitHub assigned the deployment job to the labelled self-hosted runner. |
| 11 | [Runner completed job](evidence/ci-cd/11-runner-job-succeeded.png) | The runner log records the deployment job starting and completing successfully. |
| 12 | [Successful workflow steps](evidence/ci-cd/12-deployment-workflow-succeeded.jpg) | The manually triggered workflow completed checkout, environment preparation, deployment/verification and evidence upload. |
| 13 | [Deployment artifact](evidence/ci-cd/13-deployment-artifact.jpg) | GitHub Actions retained the generated `deployment-evidence-1` artifact for download and review. |
| 14 | [Compose project after GitHub deployment](evidence/ci-cd/14-containers-after-github-deployment.png) | Docker Desktop shows the `what2do-poc` Compose project after the GitHub-triggered job. |
| 15 | [Application after GitHub deployment](evidence/ci-cd/15-app-after-github-deployment.png) | The What2Do application was reachable at `127.0.0.1:15173` after the workflow completed. |

The [supplementary local application screenshot](evidence/ci-cd/supplementary/local-app-after-deployment.png)
captures the same application after the initial manual deployment check.

## Claims Supported by the Evidence

- **Continuous integration:** PR checks ran and passed before deployment. The
  workflow definitions in `.github/workflows/backend.yml` and
  `.github/workflows/frontend.yml` automate service, integration and frontend
  checks for pushes and pull requests.
- **Continuous delivery proof of concept:** `.github/workflows/deploy-poc.yml`
  accepts a manual deployment from `main`, checks out the selected revision on a
  self-hosted runner, then calls the repeatable deployment and smoke-test scripts.
- **Containerisation and traceability:** the Compose evidence shows isolated
  application, worker and database containers. The deployment script applies a
  Git-derived image tag so the running image set is tied to a source revision.
- **Secrets handling:** `INTERNAL_API_TOKEN` is stored as an Actions secret. Its
  value is not present in this repository or in the screenshots.
- **Operational verification:** the deployment waits for services, checks three
  public health endpoints, records Compose/image state, and uploads an artifact.
- **Cost-conscious operation:** the runner was connected only for the deployment
  demonstration, using an existing laptop rather than a permanently running paid
  host. The runner can be stopped or removed once evidence has been collected.

## Curated Runtime Outputs

The three safe local pre-flight outputs are committed under
[`evidence/ci-cd/runtime/`](evidence/ci-cd/runtime/):

- [`smoke-results.json`](evidence/ci-cd/runtime/smoke-results.json) records four
  passing smoke checks;
- [`compose-ps.txt`](evidence/ci-cd/runtime/compose-ps.txt) records healthy
  containers; and
- [`compose-images.txt`](evidence/ci-cd/runtime/compose-images.txt) records the
  revision-tagged images used in that deployment.

Their [runtime-evidence note](evidence/ci-cd/runtime/README.md) records their
date, provenance and the distinction between this local pre-flight deployment and
the later GitHub-triggered deployment.

## Scope and Limits

This is a working local deployment proof of concept, not a claim of permanent
hosting, cloud autoscaling, high availability or multi-node failover. The
self-hosted runner executes trusted repository code on a laptop and must not be
used for untrusted fork pull requests. The demonstration uses Docker Compose and
local named volumes; it is therefore reproducible on the configured machine but
not a substitute for a managed production environment.

The broader `.local-data/` directory remains ignored because it can contain
machine-specific paths and deployment bookkeeping. Only the reviewed runtime
outputs above are copied into this evidence pack. The GitHub Actions artifact
shown above is the retained evidence from the successful deployment job.
