# Batch Tracker

A small system for a natural cosmetics workshop. Staff register each production **batch** (product, batch code, dates, units), see what is expired or expiring within 30 days, correct a batch, and recall it from sale. Customers use the batch code printed on their label to report **feedback**, including whether they had a skin reaction. A batch is flagged when it has at least 3 reports and more than 10% of them mention a reaction.

Assignment 1 was one Flask app with one SQLite file. In Assignment 2 it is split along the seam it already had (ADR-2, ADR-6) into two services, each with its own SQL Server database, its own migrations and its own container, plus a static UI, deployed to Azure by the pipeline.

## Live on Azure

| Part | URL |
|---|---|
| UI (Storage static website) | https://tquinnieu2024ui.z28.web.core.windows.net |
| Batches API (Container App) | https://tquinn-ieu2024-batches.lemonsand-06d134dc.francecentral.azurecontainerapps.io |
| Feedback API (Container App) | https://tquinn-ieu2024-feedback.lemonsand-06d134dc.francecentral.azurecontainerapps.io |

Both apps scale to zero, and the databases pause after an hour idle, so the first request after a quiet period can take 30 s to a minute (the UI shows "starting up" and retries; ADR-8). `GET /health` on each API answers with the commit it runs as `version`.

## Architecture

```
                 browser
                    │  static files (HTML, JS, config.js with the two API URLs)
                    ▼
     Storage static website  ── ui/ ──
                    │  fetch() from the browser, CORS allows only the UI origin
          ┌─────────┴──────────┐
          ▼                    ▼
   batches service      feedback service ──── GET /batches, GET /batches/{code}
   (Container App)      (Container App)       2 s timeout, degrades if no answer
          │                    │                         (to batches)
          ▼                    ▼
   batches database     feedback database      Azure SQL serverless, one database
   (batches_app user)   (feedback_app user)    and one contained user per service
```

Images are built by CI, tagged with the commit SHA and pushed to GHCR; CD on `main` points each Container App at that SHA. The same picture is described for machines in `system.yaml` (validated in CI against `system.schema.json` and the code).

| Service | Folder | Owns | Main logic |
|---|---|---|---|
| Batches | `services/batches/` | `dbo.batches` in its own database | create, correct (PATCH), delete and recall a batch; expiry status (`expired` / `expiring_soon` / `ok`); seed loading |
| Feedback | `services/feedback/` | `dbo.feedback` in its own database | submit a report, reaction rate per batch, flagging rule; batch details fetched from batches over HTTP |

The only link between the services is the `batch_code` text and feedback's HTTP calls to batches. There is no foreign key across the seam (ADR-3, ADR-7).

## Project structure

```
services/batches/      app.py (create_app, /health, request log, CORS), db.py, migrate.py,
                       batches/ (service.py logic, routes.py Blueprint), migrations/001_init.sql,
                       migrations/002_batch_recall.sql, seed.json, openapi.yaml, tests/, Dockerfile
services/feedback/     same layout; feedback/batches_client.py is the call to batches;
                       tests/stub_batches.py stands in for batches in the unit tests
ui/                    static pages (index, batches, feedback), app.js, config.js (written by CD)
db/init.sql            local only: one database and one login per service for compose
docker-compose.yml     SQL Server, db-init, both services and the UI on nginx
tests/integration/     cross-seam test against the real compose stack
tests/test_system_description.py   system.yaml against the schema and the code
system.yaml, system.schema.json    the system description and the course schema
.github/workflows/     ci.yml (every push and PR) and cd.yml (main only: CI, then deploy)
ADR.md, AI_USAGE.md    decision records 1-10 and the AI usage log
```

## Configuration

Each service reads environment variables only; nothing secret is in the repository.

| Variable | Service | Default | What it does |
|---|---|---|---|
| `DATABASE_URL` | both | none (required) | `mssql://user:password@host:1433/database`; on Azure a Container Apps secret set by CD |
| `PORT` | both | `8000` | Port the server listens on |
| `ALLOWED_ORIGIN` | both | `http://localhost:8080` | The only origin allowed by CORS (the UI) |
| `GIT_SHA` | both | `dev` | Returned as `version` by `/health`; CD sets it to the deployed commit |
| `BATCHES_URL` | feedback | `http://localhost:8001` | Where feedback finds the batches service |
| `BATCHES_TIMEOUT_S` | feedback | `2` | How long feedback waits for batches before degrading |
| `REACTION_ALERT_RATE` | feedback | `0.10` | Reaction rate above which a batch is flagged (with 3+ reports) |

## Run everything with Docker

Needs Docker Desktop; on Apple Silicon turn on *Use Rosetta for x86/amd64 emulation*, because SQL Server has no arm64 image.

```bash
git clone https://github.com/TatianaQuinnIE/batch-tracker.git
cd batch-tracker
docker compose up --build
```

UI on http://localhost:8080, batches API on http://localhost:8001, feedback API on http://localhost:8002 (`GET /health` on each). Compose starts SQL Server, runs `db/init.sql` once (one database and one login per service), then both services, which apply their migrations on startup. Data lives in the `mssql-data` volume, so `docker compose down` keeps it and `docker compose down -v` deletes it.

**Run one service on its own** (SQL Server from compose, the service with Python 3.12):

```bash
docker compose up -d db db-init
cd services/batches
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL='mssql://batches_app:LocalOnly-Batches-2026@localhost:1433/batches' PORT=8001 python app.py
```

(The local passwords are for the compose database only, which listens on 127.0.0.1; Azure uses generated passwords kept in GitHub secrets.)

## The cross-seam flow and partial failure

The feedback page (http://localhost:8080/feedback.html) shows each batch's product and expiry next to its reaction rate. Feedback fetches them from batches over HTTP with a 2 s timeout (`GET /batches` for lists, `GET /batches/{code}` for one batch) and joins them in code by `batch_code`. If batches does not answer in time, feedback still returns every report, rate and flag from its own database, with `batch: null`, `batches_service: "unavailable"` and the notice *"Batch details are unavailable right now"*, and logs a warning. Try `docker compose stop batches` and reload; `docker compose start batches` brings the details back. ADR-6 explains the choice, ADR-10 what I deliberately did not build on top of it.

## Pages and endpoints

The full contracts are `services/batches/openapi.yaml` and `services/feedback/openapi.yaml` (OpenAPI 3.1, validated in CI and checked against the real routes by the tests).

| Method | Path | Does |
|---|---|---|
| GET | `/batches` | All batches with their expiry status (and recall fields after migration 002) |
| GET | `/batches/expiring-soon` | Batches expiring within 30 days |
| GET | `/batches/<batch_code>` | One batch (404 if unknown) |
| POST | `/batches` | Registers a batch (validated; 400 with a message if a field is wrong or the code already exists) |
| PATCH | `/batches/<batch_code>` | Corrects `product`, `expires_on` and/or `quantity`; `batch_code` never changes |
| POST | `/batches/<batch_code>/recall` | Recalls a batch today with `{"reason": ...}`; once per batch |
| DELETE | `/batches/<batch_code>` | Removes a batch registered by mistake (204) |
| GET | `/feedback` | Per-batch summaries (reports, reactions, rate, flag) with batch details from batches |
| GET | `/feedback/flagged` | Only the flagged batches |
| GET | `/feedback/<batch_code>` | Summary for one batch (404 if no feedback) |
| POST | `/feedback` | Submits a report (the code does not have to be registered yet, ADR-3) |
| GET | `/health` | Both services: `status`, `db`, `version` (commit SHA); batches also `schema` (last migration applied). 503 if the database is unreachable |

UI pages: `index.html` (home), `batches.html` (list, register, recall), `feedback.html` (customer form and workshop view).

**Logs.** Every request is logged by each service as one line, `METHOD path status duration_ms`, plus migrations applied, seeding, database retries and the feedback → batches degradations. On Azure: `az containerapp logs show --name tquinn-ieu2024-feedback --resource-group rg-tquinn-ieu2024 --follow`.

## Tests, lint and coverage

Per service, against the SQL Server from compose; the tests create and migrate their own `batches_test` / `feedback_test` database:

```bash
docker compose up -d db
cd services/batches            # or services/feedback
pip install -r requirements-dev.txt
ruff check --config ../../ruff.toml .
TEST_DATABASE_URL='mssql://sa:LocalOnly-Sa-2026@localhost:1433/master' \
  pytest --cov=batches --cov=migrate --cov=db --cov-report=term-missing --cov-fail-under=70
```

Feedback's unit tests replace batches with a stub HTTP server (`tests/stub_batches.py`) that can be made slow, broken or stopped. The cross-seam integration test runs against the real compose stack and stops and restarts the batches container:

```bash
docker compose up -d --build
pip install pytest==8.3.4
pytest -v tests/integration
```

Results in CI on 2026-11-21 (CD run on e000feb): batches 87 passed, 99.6% coverage; feedback 69 passed, 98.1% coverage; system description 12 passed; integration 2 passed. What is deliberately not tested (the UI's JavaScript, Azure-only behaviour) is in ADR-9.

## CI/CD

- **CI** (`.github/workflows/ci.yml`, every push to a branch and every pull request): `test` per service (ruff, then pytest against a throwaway SQL Server with a random password, failing under 70% coverage), `describe` (system.yaml and both OpenAPI files), `integration` (the compose stack and the cross-seam test) and `images` (both images built on every run; pushed to GHCR tagged with the commit SHA only when CD calls CI on `main`). It never touches Azure (ADR-9).
- **CD** (`.github/workflows/cd.yml`, only on `main`, so only after a merged pull request): runs the whole CI on the same commit, signs in to Azure with OIDC as a managed identity (no Azure password in GitHub), sets each app's database secret, deploys the SHA-tagged images as a new revision, writes `ui/config.js`, uploads `ui/` to the static website, and waits for both `/health` endpoints to answer 200 with the deployed commit as `version`, failing the run otherwise (ADR-8).


## Azure: initial setup (run once, by hand)

After this setup only the pipeline changes anything (ADR-8). These are the exact commands I ran, in **Bash** (`bash` first on a Mac: zsh reads `:r` in `"repo:$GH_REPO:ref…"` as a modifier and breaks the federated credential). No password is written in any file: the two database passwords are generated in the shell and go straight into GitHub secrets, and the SQL administrator password is typed at a prompt and kept only in my password manager.

**0. Names**

```bash
bash
PREFIX=tquinn-ieu2024                  # IE username with . replaced by -
RG=rg-$PREFIX
UI_STORAGE=tquinnieu2024ui
SQL_SERVER=$PREFIX-sql
SQL_ADMIN=tquinnadmin
GH_REPO=TatianaQuinnIE/batch-tracker
```

**1. Subscription and region**

```bash
az login
az account set --subscription "Azure for Students"
az policy assignment list \
  --query "[?displayName=='Allowed resource deployment regions'].parameters.listOfAllowedLocations.value" -o tsv
REGION=<one region from that list>
SQL_REGION=$REGION                     # another region from the list only if the free offer is refused
```

**2. Providers and resource group**

```bash
az extension add --name containerapp --upgrade
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.Sql Microsoft.Storage Microsoft.ManagedIdentity; do
  az provider register --namespace "$ns" --wait
done
az group create --name "$RG" --location "$REGION"
```

**3. The UI: a Storage static website**

```bash
az storage account create --name "$UI_STORAGE" --resource-group "$RG" --location "$REGION" \
  --kind StorageV2 --sku Standard_LRS
az storage blob service-properties update --account-name "$UI_STORAGE" --auth-mode key \
  --static-website --index-document index.html
UI_ORIGIN=$(az storage account show -n "$UI_STORAGE" -g "$RG" --query primaryEndpoints.web -o tsv)
UI_ORIGIN=${UI_ORIGIN%/}; echo "$UI_ORIGIN"     # the public URL, also in system.yaml
```

**4. SQL server, two serverless databases on the free offer, one contained user each**

```bash
read -rs -p "SQL admin password: " SQL_ADMIN_PASSWORD; echo
az sql server create --name "$SQL_SERVER" --resource-group "$RG" --location "$SQL_REGION" \
  --admin-user "$SQL_ADMIN" --admin-password "$SQL_ADMIN_PASSWORD"
for svc in batches feedback; do
  az sql db create --resource-group "$RG" --server "$SQL_SERVER" --name "$PREFIX-$svc-db" \
    --edition GeneralPurpose --compute-model Serverless --family Gen5 \
    --min-capacity 0.5 --capacity 1 --backup-storage-redundancy Local \
    --use-free-limit true --free-limit-exhaustion-behavior AutoPause
done
az sql server firewall-rule create -g "$RG" -s "$SQL_SERVER" -n AllowAzureServices \
  --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0

# Open the firewall to my IP only while creating the users
MY_IP=$(curl -s https://api.ipify.org)
az sql server firewall-rule create -g "$RG" -s "$SQL_SERVER" -n setup-my-ip \
  --start-ip-address "$MY_IP" --end-ip-address "$MY_IP"

# Letters and digits only (upper, lower, digit), so no URL-encoding surprises
BATCHES_DB_PASSWORD="Bt$(openssl rand -hex 12)Q7"
FEEDBACK_DB_PASSWORD="Fb$(openssl rand -hex 12)Q7"

# sqlcmd from the SQL Server image (Docker Desktop running; sqlcmd is not installed locally)
sqlcmd_azure() {
  docker run --rm --platform linux/amd64 -e SQLCMDPASSWORD="$SQL_ADMIN_PASSWORD" \
    --entrypoint /opt/mssql-tools18/bin/sqlcmd mcr.microsoft.com/mssql/server:2022-latest \
    -S "$SQL_SERVER.database.windows.net" -U "$SQL_ADMIN" -b "$@"
}
for svc in batches feedback; do
  if [ "$svc" = batches ]; then pw=$BATCHES_DB_PASSWORD; else pw=$FEEDBACK_DB_PASSWORD; fi
  sqlcmd_azure -d "$PREFIX-$svc-db" -Q "CREATE USER ${svc}_app WITH PASSWORD = '$pw';
    ALTER ROLE db_ddladmin ADD MEMBER ${svc}_app;
    ALTER ROLE db_datareader ADD MEMBER ${svc}_app;
    ALTER ROLE db_datawriter ADD MEMBER ${svc}_app;"
done

az sql server firewall-rule delete -g "$RG" -s "$SQL_SERVER" -n setup-my-ip
```

**5. Container Apps (placeholder image until the first deploy)**

```bash
az containerapp env create --name "$PREFIX-env" --resource-group "$RG" --location "$REGION"

az containerapp create --name "$PREFIX-batches" --resource-group "$RG" --environment "$PREFIX-env" \
  --image mcr.microsoft.com/k8se/quickstart:latest \
  --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi \
  --secrets "database-url=mssql://batches_app:${BATCHES_DB_PASSWORD}@${SQL_SERVER}.database.windows.net:1433/${PREFIX}-batches-db" \
  --env-vars PORT=8000 DATABASE_URL=secretref:database-url ALLOWED_ORIGIN="$UI_ORIGIN"
BATCHES_URL=https://$(az containerapp show -n "$PREFIX-batches" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)

az containerapp create --name "$PREFIX-feedback" --resource-group "$RG" --environment "$PREFIX-env" \
  --image mcr.microsoft.com/k8se/quickstart:latest \
  --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi \
  --secrets "database-url=mssql://feedback_app:${FEEDBACK_DB_PASSWORD}@${SQL_SERVER}.database.windows.net:1433/${PREFIX}-feedback-db" \
  --env-vars PORT=8000 DATABASE_URL=secretref:database-url ALLOWED_ORIGIN="$UI_ORIGIN" \
             BATCHES_URL="$BATCHES_URL" BATCHES_TIMEOUT_S=2
```

**6. The pipeline's identity (user-assigned managed identity + federated credentials)**

```bash
az identity create --name "$PREFIX-github" --resource-group "$RG" --location "$REGION"
CLIENT_ID=$(az identity show -n "$PREFIX-github" -g "$RG" --query clientId -o tsv)
PRINCIPAL_ID=$(az identity show -n "$PREFIX-github" -g "$RG" --query principalId -o tsv)
RG_ID=$(az group show -n "$RG" --query id -o tsv)
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope "$RG_ID"

# GitHub may send the subject with names or with numeric IDs: register both.
OWNER_ID=$(gh api "repos/${GH_REPO}" --jq .owner.id)
REPO_ID=$(gh api "repos/${GH_REPO}" --jq .id)
az identity federated-credential create --name github-main --identity-name "$PREFIX-github" -g "$RG" \
  --issuer https://token.actions.githubusercontent.com --audiences api://AzureADTokenExchange \
  --subject "repo:${GH_REPO}:ref:refs/heads/main"
az identity federated-credential create --name github-main-ids --identity-name "$PREFIX-github" -g "$RG" \
  --issuer https://token.actions.githubusercontent.com --audiences api://AzureADTokenExchange \
  --subject "repo:${GH_REPO%%/*}@${OWNER_ID}/${GH_REPO#*/}@${REPO_ID}:ref:refs/heads/main"
az identity federated-credential list --identity-name "$PREFIX-github" -g "$RG" --query "[].subject" -o tsv
```

**7. GitHub secrets and variables**

```bash
gh secret set AZURE_CLIENT_ID       -R "$GH_REPO" --body "$CLIENT_ID"
gh secret set AZURE_TENANT_ID       -R "$GH_REPO" --body "$(az account show --query tenantId -o tsv)"
gh secret set AZURE_SUBSCRIPTION_ID -R "$GH_REPO" --body "$(az account show --query id -o tsv)"
gh secret set BATCHES_DB_PASSWORD   -R "$GH_REPO" --body "$BATCHES_DB_PASSWORD"
gh secret set FEEDBACK_DB_PASSWORD  -R "$GH_REPO" --body "$FEEDBACK_DB_PASSWORD"
gh variable set PREFIX         -R "$GH_REPO" --body "$PREFIX"
gh variable set RESOURCE_GROUP -R "$GH_REPO" --body "$RG"
gh variable set UI_STORAGE     -R "$GH_REPO" --body "$UI_STORAGE"
unset SQL_ADMIN_PASSWORD BATCHES_DB_PASSWORD FEEDBACK_DB_PASSWORD
```

**8. Images Azure can pull.** The CI images job builds with `provenance: false`. On GitHub, Packages → `batch-tracker-batches` and `batch-tracker-feedback` → Package settings → Change visibility → **Public** (they hold no secrets).

**9. Read access for the professors**

```bash
for prof in amartini@faculty.ie.edu bserra@faculty.ie.edu; do
  az role assignment create --assignee "$prof" --role Reader --scope "$RG_ID"
done
```

From here, every merge to `main` runs CD (`.github/workflows/cd.yml`): the whole CI, then the deploy of that commit, then a health check that `/health` on both services answers 200 with the deployed commit as `version`. Logs: `az containerapp logs show --name tquinn-ieu2024-feedback --resource-group rg-tquinn-ieu2024 --follow` (add `--type system` for start-up and probe events).

## Migration 002 on Azure (evidence)

`002_batch_recall.sql` adds `recalled_on` and `recall_reason` to `dbo.batches` (ADR-7). It was deployed through the pipeline to a database that already had data, and applied by the batches service on startup like 001.

**Before the deploy** (2026-11-21, revision on commit 6d2458a, schema 001 only):

```
$ curl -s https://tquinn-ieu2024-batches.lemonsand-06d134dc.francecentral.azurecontainerapps.io/health
{"db":"ok","status":"ok","version":"6d2458a076144b88381d5c0738314887e9c4c9fc"}

$ curl -s .../batches      # 4 rows, without the 002 fields
CAL-2603 8   ROS-2608 45   ALO-2609 60   LAV-2607 120
```

**After the deploy** (2026-11-21, PR #7 merged as a721753, CD run 44907329909 green). The CD log's health check, which only passes on the deployed commit:

```
batches healthy on a7217538f483da2f6d6eb612d7ebd480b84b29bf: {"db":"ok","schema":"002_batch_recall.sql","status":"ok","version":"a7217538f483da2f6d6eb612d7ebd480b84b29bf"}
feedback healthy on a7217538f483da2f6d6eb612d7ebd480b84b29bf: {"db":"ok","status":"ok","version":"a7217538f483da2f6d6eb612d7ebd480b84b29bf"}
```

And the batches API afterwards: the rows from before are all still there with the same quantities, and now carry the 002 fields as null (not recalled):

```
$ curl -s .../batches      # batch_code quantity recalled_on recall_reason
CAL-2603 8   None None
ROS-2608 45  None None
ALO-2609 60  None None
LAV-2607 120 None None
LAV-2610 30  None None     # added through the UI
```

The batches log on Azure shows the migration applied once, about 0.1 s, on the first start of the new revision:

```
$ az containerapp logs show --name tquinn-ieu2024-batches --resource-group rg-tquinn-ieu2024 --tail 300 --format text | grep migration
2026-11-21 13:11:11,697 INFO migrate applying migration 002_batch_recall.sql
2026-11-21 13:11:11,800 INFO migrate applied migration 002_batch_recall.sql
```
