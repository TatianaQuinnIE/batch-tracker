# Batch Tracker

> **Assignment 2 (in progress).** The monolith is split into two services, `services/batches/` and `services/feedback/`, each with its own Dockerfile, dependencies, migrations, tests and SQL Server database. The UI becomes static files in `ui/`. The sections after this box still describe the Assignment 1 monolith and will be rewritten.
>
> **Run everything** (needs Docker Desktop; on Apple Silicon turn on *Use Rosetta for x86/amd64 emulation*, because SQL Server has no arm64 image):
>
> ```bash
> docker compose up --build
> ```
>
> UI on http://localhost:8080, batches API on http://localhost:8001, feedback API on http://localhost:8002 (`GET /health` on each). Compose starts SQL Server, runs `db/init.sql` once (one database and one login per service), then both services, which apply their migrations on startup. Data lives in the `mssql-data` volume, so `docker compose down` keeps it and `docker compose down -v` deletes it.
>
> **Run one service on its own** (SQL Server from compose, the service with Python 3.12):
>
> ```bash
> docker compose up -d db db-init
> cd services/batches
> python3.12 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> DATABASE_URL='mssql://batches_app:LocalOnly-Batches-2026@localhost:1433/batches' PORT=8001 python app.py
> ```
>
> **Tests, lint and coverage** (per service, against the SQL Server from compose; the tests create and migrate their own `batches_test` / `feedback_test` database):
>
> ```bash
> docker compose up -d db
> cd services/batches            # or services/feedback
> pip install -r requirements-dev.txt
> ruff check --config ../../ruff.toml .
> TEST_DATABASE_URL='mssql://sa:LocalOnly-Sa-2026@localhost:1433/master' \
>   pytest --cov=batches --cov=migrate --cov=db --cov-report=term-missing --cov-fail-under=70
> ```
>
> Result on 2026-11-19: batches 58 passed, 99% coverage; feedback 69 passed, 98% coverage. Feedback's tests replace the batches service with a stub HTTP server (`tests/stub_batches.py`) that can be made slow, broken or stopped.
>
> **Cross-seam integration test** (against the real compose stack; it stops and restarts the batches container):
>
> ```bash
> docker compose up -d --build
> pip install pytest==8.3.4
> pytest -v tests/integration
> ```
>
> **The cross-seam flow and partial failure.** The feedback page (http://localhost:8080/feedback.html) shows each batch's product and expiry next to its reaction rate; feedback fetches them from batches over HTTP with a 2 s timeout (`BATCHES_TIMEOUT_S`). Try `docker compose stop batches` and reload: feedback still lists every report, with the notice *"Batch details are unavailable right now"*, and the batches page says the service is starting up and retries. `docker compose start batches` brings the details back.
>
> **API description:** `services/batches/openapi.yaml` and `services/feedback/openapi.yaml` (OpenAPI 3.1, validated in CI and checked against the real routes by the tests).

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

A small web app for a natural cosmetics workshop. Staff register each production **batch** (product, batch code, dates, units) and see what is expired or expiring within 30 days. Customers use the batch code printed on their label to report **feedback**, including whether they had a skin reaction. A batch is flagged when it has at least 3 reports and more than 10% of them mention a reaction.

The app is one Flask process with one SQLite file. It has two feature domains that only share the `batch_code` text, so they can be split into separate services in Assignment 2.

## Feature domains

| Domain | Package | Owns | Main logic |
|---|---|---|---|
| Batches | `batches/` | `batches` table | create batch with validation, expiry status (`expired` / `expiring_soon` / `ok`), seed loading |
| Feedback | `feedback/` | `feedback` table | submit report, reaction rate per batch, flagging rule |

`feedback/` never imports from `batches/` and never queries the `batches` table. `app.py` is the only place that knows about both: it creates the schema for each domain and registers both Blueprints. That is where the split would happen.

## Project structure

```
app.py               entry point: create_app(), reads PORT and DATA_DIR
db.py                opens the SQLite connection
seed.json            starter batches, loaded only when the table is empty
batches/             service.py (logic), routes.py (Blueprint), templates/
feedback/            service.py (logic), routes.py (Blueprint), templates/
templates/           base.html, index.html (shared layout)
tests/               unit tests (services) and route tests
Dockerfile           course template with the four TODOs filled in
ADR.md               architecture decision records
AI_USAGE.md          AI usage log
```

## Configuration

Everything is configured with environment variables. None are required.

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8000` | Port the server listens on (always on `0.0.0.0`) |
| `DATA_DIR` | `./data` (the Dockerfile sets `/data`) | Folder for the SQLite file; created on first start |
| `REACTION_ALERT_RATE` | `0.10` | Reaction rate above which a batch is flagged (with 3+ reports) |

**SQLite path:** `$DATA_DIR/tracker.db`. The schema is created on first start with `CREATE TABLE IF NOT EXISTS`, and `seed.json` is loaded only when the `batches` table is empty, so restarting never duplicates or deletes data.

## Run it on your machine

Requires Python 3.12 or newer.

```bash
git clone https://github.com/TatianaQuinnIE/batch-tracker.git
cd batch-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000. To use another port or data folder: `PORT=9000 DATA_DIR=/tmp/bt python app.py`.

## Run it with Docker

```bash
docker build -t batch-tracker .
docker run -p 8000:8000 -v batch-tracker-data:/data batch-tracker
```

Open http://localhost:8000. The named volume keeps the database when the container is removed. Another port: `docker run -e PORT=9000 -p 9000:9000 -v batch-tracker-data:/data batch-tracker`.

## Pages and endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/` | Home page |
| GET / POST | `/batches/` | Batch list and "register a batch" form |
| GET | `/batches/expiring-soon` | JSON list of batches expiring within 30 days |
| GET / POST | `/feedback/` | Customer feedback form and the workshop view |
| GET | `/feedback/flagged` | JSON list of flagged batches |
| GET | `/feedback/<batch_code>` | JSON summary for one batch (404 if no feedback) |

Batches API, added in Assignment 2 with migration 002 (full list in `services/batches/openapi.yaml`):

| Method | Path | Does |
|---|---|---|
| POST | `/batches/<batch_code>/recall` | Recalls a batch today with `{"reason": ...}`; once per batch |
| PATCH | `/batches/<batch_code>` | Corrects `product`, `expires_on` and/or `quantity` |
| DELETE | `/batches/<batch_code>` | Removes a batch registered by mistake (204) |

## Migration 002 on Azure (evidence)

`002_batch_recall.sql` adds `recalled_on` and `recall_reason` to `dbo.batches` (ADR-10). It was deployed through the pipeline to a database that already had data, and applied by the batches service on startup like 001.

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

## Tests and coverage

```bash
pytest --cov=batches --cov=feedback --cov-report=term-missing
```

Result on 2026-10-12: **31 passed, 100% coverage** of the `batches` and `feedback` packages.

```
Name                   Stmts   Miss  Cover   Missing
----------------------------------------------------
batches/__init__.py        0      0   100%
batches/routes.py         27      0   100%
batches/service.py        44      0   100%
feedback/__init__.py       0      0   100%
feedback/routes.py        34      0   100%
feedback/service.py       40      0   100%
----------------------------------------------------
TOTAL                    145      0   100%
```

See ADR-4 in `ADR.md` for what the tests focus on and what they leave out.

## Container contract check (§7)

Output of the course checker `container/run.sh` against this repository on 2026-10-12:

```
=== SDD Assignment 1 contract check ===
Repository: /Users/tatianaquinn/Desktop/batch-tracker

==> Repository shape
  PASS  one Dockerfile, one manifest (requirements.txt)

==> Build from a clean context, no build args
  PASS  image built
  PASS  image size 50 MB

==> Start on PORT=8000 and reach it from the host
  PASS  HTTP 200 from http://localhost:8000/

==> SQLite file under DATA_DIR
  PASS  found in /data: tracker.db 

==> Data persists, and a second boot does not re-seed
  PASS  volume at /data persists
  PASS  row counts unchanged across restart: batches=4 feedback=0 

==> PORT override is honoured (not hardcoded)
  PASS  HTTP 200 from http://localhost:9123/

=== ALL CHECKS PASSED ===
Paste this output into your README as the §7 evidence.
```
