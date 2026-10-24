# On-Demand Laptop Deployment

## Prerequisites

- Windows 10 or 11 with Docker Desktop running Linux containers;
- Git and PowerShell 7 (Windows PowerShell 5.1 should also work);
- Docker Compose v2 (`docker compose version`);
- enough free resources for the full integration stack;
- internet access for the first image build.

Ollama is optional for this proof. The baseline configuration uses deterministic
rules-based interpretation so the deployment pipeline can be demonstrated first.

## First local deployment

From the repository root:

```powershell
Copy-Item .env.deploy.example .env.deploy
```

Open `.env.deploy` and replace `replace-with-a-long-random-token` with a random value
of at least 16 characters. The file is ignored by Git. Then run:

```powershell
./scripts/deploy.ps1
```

The command builds revision-tagged application images, starts the databases and
migrations, waits for service health, and checks the three public endpoints. Open
<http://127.0.0.1:15173> after it succeeds.

Generated evidence is placed under `.local-data/deploy/evidence/<UTC timestamp>/`:

- `smoke-results.json` records endpoint and Compose-state checks;
- `compose-ps.txt` records service health and status;
- `compose-images.txt` records the deployed images and tags;
- `failure-logs.txt` is written when deployment fails.

Stop the demonstration without deleting its databases:

```powershell
docker compose -p what2do-poc --env-file .env.deploy `
  -f compose.integration.yaml -f compose.deploy.yaml down
```

Do not add `-v` unless intentionally deleting all demonstration data.

## Temporary GitHub runner

1. In the GitHub repository, open **Settings > Actions > Runners**.
2. Select **New self-hosted runner**, then choose Windows and the laptop architecture.
3. Run GitHub's displayed download and configuration commands in a dedicated folder
   outside this repository.
4. During configuration, add the custom label `what2do-deploy`.
5. Do not install the runner as a Windows service for this temporary demonstration.
6. Add a repository Actions secret named `INTERNAL_API_TOKEN` containing a random
   value of at least 16 characters.
7. Start Docker Desktop, then start the runner interactively with `./run.cmd`.
8. On GitHub Actions, choose **Deploy proof of concept**, select `main`, and click
   **Run workflow**.
9. Download the deployment evidence artifact after the job succeeds.
10. Stop the runner with Ctrl+C when the demonstration is complete.

The workflow deliberately runs only on `[self-hosted, Windows, X64,
what2do-deploy]`. If GitHub assigned a different architecture label, update that one
label in `.github/workflows/deploy-poc.yml`.

## Rollback drill

Run two successful deployments with different Git revisions so both image sets remain
on the laptop. Then execute:

```powershell
./scripts/rollback.ps1
```

Rollback selects the previously recorded image tag, recreates the application
containers without rebuilding, and repeats the smoke checks. It does not roll database
schemas backward; migrations in this project must therefore remain backward-compatible
with the immediately preceding application revision.

## Troubleshooting

Inspect status and logs with:

```powershell
docker compose -p what2do-poc --env-file .env.deploy `
  -f compose.integration.yaml -f compose.deploy.yaml ps
docker compose -p what2do-poc --env-file .env.deploy `
  -f compose.integration.yaml -f compose.deploy.yaml logs --tail 200
```

If a deployment job remains queued, start `run.cmd` and confirm that the runner has
the `what2do-deploy` label. If Ollama is enabled later, start Ollama on the host, pull
the configured model, and verify that `host.docker.internal:11434` is reachable from
Docker containers.
