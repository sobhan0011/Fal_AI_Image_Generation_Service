# FastAPI + fal.ai Image Generation

A production-minded FastAPI service for asynchronous image generation with fal.ai, transactional AI credits, signed webhooks, idempotent refunds, SQLAlchemy, Alembic, Docker, and PostgreSQL-ready deployment.

The project is organized with a NestJS-like separation of concerns:

```text
HTTP
  ↓
controllers/
  ↓
application/
  ↓
ports
  ↓
infrastructure/
   ├── database/
   └── fal/
```

## Features

- `POST /generate/image`
  - validates the user;
  - atomically debits AI balance;
  - submits an image generation request to fal.ai asynchronously;
  - uses a webhook instead of polling;
  - stores a `GenerationJob` in `IN_QUEUE`;
  - rolls back the debit if fal submission fails.
- `POST /generate/image/callback`
  - optionally verifies the fal webhook signature;
  - marks successful jobs as `SUCCESS`;
  - stores the generated image URL;
  - marks failed jobs as `FAILED`;
  - refunds failed generations exactly once;
  - safely handles duplicate and concurrent callbacks.
- `GET /my-files/{user_id}`
  - returns the user's current balance;
  - returns the user's full generation history, including `IN_QUEUE`, `SUCCESS`, and `FAILED` jobs.
- SQLite for local development.
- PostgreSQL support for deployment.
- Alembic for database migrations.
- Docker support.
- Automatic Render callback URL resolution through `RENDER_EXTERNAL_URL`.
- fal.ai isolated behind an application port so tests can use a fake gateway without spending credits.
- `/` redirects to `/docs` for convenient Swagger access.

## Architecture

```text
app/
├── main.py
├── config.py
│
├── controllers/
│   ├── __init__.py
│   ├── dependencies.py
│   ├── exception_handlers.py
│   ├── generation_controller.py
│   ├── files_controller.py
│   ├── health_controller.py
│   └── schemas.py
│
├── application/
│   ├── errors.py
│   ├── generation_service.py
│   ├── models.py
│   └── ports.py
│
└── infrastructure/
    ├── database/
    │   ├── database.py
    │   ├── models.py
    │   └── unit_of_work.py
    │
    └── fal/
        ├── gateway.py
        └── webhook.py

alembic/
scripts/
├── __init__.py
└── seed.py

tests/
├── __init__.py
├── conftest.py
├── fakes.py
├── helpers.py
├── test_generation.py
├── test_callback.py
└── test_files.py

Dockerfile
alembic.ini
pyproject.toml
```

### `controllers/`

The HTTP layer.

It owns:

- FastAPI routers;
- request/response schemas;
- dependency extraction from `app.state`;
- webhook transport validation;
- application-exception → HTTP-response mapping.

Controllers should not contain wallet or generation business logic.

### `application/`

The business/application layer.

`GenerationService` owns the workflow:

1. debit the user;
2. submit the request to fal.ai;
3. create the generation job;
4. process callback success/failure;
5. request exactly-once refund behavior.

It does not depend directly on FastAPI, SQLAlchemy, `fal_client`, or PyNaCl.

`ports.py` defines the interfaces required by the application, including:

- `FalGateway`
- `GenerationUnitOfWork`
- `GenerationUnitOfWorkFactory`

### `infrastructure/`

Everything that talks to external technology.

`database/` contains:

- SQLAlchemy models;
- async engine/session setup;
- concrete unit-of-work implementation.

`fal/` contains:

- the `fal_client` gateway;
- webhook signature verification.

The application depends on abstractions while infrastructure provides the implementations.

## Data model

### `User`

- `id` — UUID
- `ai_balance` — `Decimal` / SQL `NUMERIC(12, 2)`

### `GenerationJob`

- `id`
- `request_id` — unique fal request ID
- `user_id` — UUID foreign key
- `prompt`
- `aspect_ratio`
- `status` — `IN_QUEUE`, `SUCCESS`, or `FAILED`
- `cost`
- `is_refunded`
- `request_url` — generated image URL, nullable
- `error_message` — nullable
- `created_at`
- `updated_at`

## API

### `POST /generate/image`

Example request:

```json
{
  "user_id": "11111111-1111-1111-1111-111111111111",
  "prompt": "image of a cat with big ears",
  "aspect_ratio": "1:1"
}
```

Successful response:

```json
{
  "request_id": "fal-request-id",
  "status": "IN_QUEUE",
  "cost": "50.00"
}
```

Behavior:

1. Validate that the user exists.
2. Atomically debit the configured generation cost.
3. Submit the request to fal.ai using the configured webhook URL.
4. Store the generation job as `IN_QUEUE`.
5. Commit the transaction.

If the user does not exist, the API returns `404`.

If the user does not have enough balance, the API returns `400` and no credits are deducted.

If fal submission fails, the surrounding SQL transaction rolls back and the API returns the mapped fal submission error response.

---

### `POST /generate/image/callback`

Successful callback example:

```json
{
  "request_id": "fal-request-id",
  "status": "OK",
  "payload": {
    "images": [
      {
        "url": "https://cdn.example/image.png"
      }
    ]
  }
}
```

The job becomes `SUCCESS` and the first generated image URL is stored in `request_url`.

Failure callback example:

```json
{
  "request_id": "fal-request-id",
  "status": "ERROR",
  "error": "generation failed",
  "payload": null
}
```

The job becomes `FAILED`, `is_refunded=true`, and the original job cost is credited back to the user.

Callbacks are idempotent: once a job leaves `IN_QUEUE`, later duplicate or conflicting callbacks do not mutate it again.

---

### `GET /my-files/{user_id}`

Returns:

- `user_id`
- current `ai_balance`
- generation history

The history can contain:

- `IN_QUEUE`
- `SUCCESS`
- `FAILED`

This endpoint is a generation-history endpoint rather than a success-only file list.

---

### `GET /health`

Health-check endpoint for local development and deployment.

---

### `/`

Redirects to:

```text
/docs
```

## Exactly-once refund behavior

A naive implementation such as:

```python
if job.status == IN_QUEUE:
    job.status = FAILED
    user.ai_balance += job.cost
```

is unsafe because two callbacks can observe the same state concurrently and both refund the wallet.

The database layer instead performs a conditional state transition similar to:

```sql
UPDATE generation_jobs
SET status = 'FAILED',
    is_refunded = true
WHERE request_id = :request_id
  AND status = 'IN_QUEUE'
  AND is_refunded = false;
```

Only one transaction can claim the transition.

The winning transaction then performs the wallet increment in the same database transaction:

```sql
UPDATE users
SET ai_balance = ai_balance + :cost
WHERE id = :user_id;
```

This protects against duplicate webhook deliveries and concurrent failure callbacks.

Success processing follows the same terminal-state principle: only a job currently in `IN_QUEUE` may transition to `SUCCESS`.

## Balance handling

Wallet values use Python `Decimal` and SQL `NUMERIC(12, 2)` instead of binary floating-point.

Generation debit is performed atomically:

```sql
UPDATE users
SET ai_balance = ai_balance - :cost
WHERE id = :user_id
  AND ai_balance >= :cost;
```

This prevents concurrent generation requests from both spending the same balance.

## Distributed transaction trade-off

The SQL database and fal.ai queue cannot participate in one atomic distributed transaction.

The current flow keeps the database unit of work open while submitting to fal.ai. If fal submission raises, the database transaction rolls back the debit.

A rare failure after fal.ai accepts the request but before the SQL transaction commits could still leave an orphan remote generation. In that case the user is not charged, but the service owner could pay for a generation that is not represented locally.

For a larger financial system, consider:

- a wallet ledger;
- internal generation IDs;
- an outbox/saga workflow;
- reconciliation for orphan remote jobs.

## Configuration

Settings are loaded using `pydantic-settings`.

Typical local `.env`:

```env
DATABASE_URL=sqlite+aiosqlite:///./app.db

FAL_KEY=your_fal_key
FAL_MODEL=fal-ai/nano-banana

FAL_WEBHOOK_URL=http://localhost:8000/generate/image/callback
FAL_VERIFY_WEBHOOK_SIGNATURES=true

IMAGE_GENERATION_COST=50.00
SEED_DEMO_USERS=true
DEMO_USER_BALANCE=1000.00
```

Never commit `.env` or your `FAL_KEY`.

### Webhook URL resolution

`FAL_WEBHOOK_URL` is optional in deployed environments.

The application resolves the webhook URL in this order:

1. explicit `FAL_WEBHOOK_URL`, if configured;
2. `RENDER_EXTERNAL_URL + /generate/image/callback`, when running on Render;
3. local fallback: `http://localhost:8000/generate/image/callback`.

This lets local tests inject their own callback URL while Render deployments automatically use the public service URL.

For real fal.ai webhook delivery, the callback must be publicly reachable over HTTPS. `localhost` works only for local/simulated callback testing.

## Local development

Requires Python 3.11+.

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project with development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Apply migrations:

```powershell
alembic upgrade head
```

Optionally seed demo users:

```powershell
python -m scripts.seed
```

Run the API:

```powershell
python -m uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/
```

which redirects to:

```text
http://127.0.0.1:8000/docs
```

## Demo users

The seed script can create deterministic UUID demo users such as:

```text
11111111-1111-1111-1111-111111111111
22222222-2222-2222-2222-222222222222
```

Their starting balance is controlled by `DEMO_USER_BALANCE`.

Demo seeding is intended for development/testing only.

## Tests

The test suite is separated by API responsibility:

```text
tests/
├── conftest.py
├── fakes.py
├── helpers.py
├── test_generation.py
├── test_callback.py
└── test_files.py
```

Run:

```powershell
python -m pytest -v
```

The pytest configuration uses:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]
addopts = "--basetemp=.pytest_tmp"
```

The custom base temp directory avoids the Windows pytest temp-directory permission issue encountered during development.

The tests use `FakeFalGateway`, so they do not make real fal.ai requests and do not spend fal credits.

Current coverage includes:

### Generation

- queued job creation;
- balance debit;
- unknown user;
- insufficient balance;
- rollback when fal submission fails.

### Callback

- success callback;
- failed callback and refund;
- duplicate failed callback;
- concurrent duplicate failed callbacks;
- multiple failed jobs refund independently;
- failure after success is ignored;
- success after failure is ignored.

### Files/history

- successful jobs appear in history;
- failed jobs appear in history;
- queued jobs appear in history;
- all generation statuses are returned;
- successful jobs contain the stored image URL.

## Alembic

Database schema changes are managed through Alembic rather than calling `Base.metadata.create_all()` during application startup.

Create a migration:

```powershell
alembic revision --autogenerate -m "describe change"
```

Apply migrations:

```powershell
alembic upgrade head
```

Check current revision:

```powershell
alembic current
```

## Docker

Build:

```powershell
docker build -t fal-image-api .
```

Run locally:

```powershell
docker run --rm --name fal-image-api-test -p 8000:8000 --env-file .env fal-image-api
```

The Docker image runs migrations before starting Uvicorn:

```text
alembic upgrade head
→
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

The image installs production dependencies from `pyproject.toml`; development dependencies such as pytest and Ruff are not required in the deployed container.

## Render deployment

The project can be deployed to Render as a Docker Web Service with Render PostgreSQL.

Recommended setup:

1. Create a Render PostgreSQL database.
2. Create a Render Web Service from the GitHub repository.
3. Select Docker as the runtime.
4. Use the same Render region for the web service and database.
5. Configure environment variables.
6. Deploy.

Example Render environment variables:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/DATABASE

FAL_KEY=your_raw_fal_key
FAL_MODEL=fal-ai/nano-banana
FAL_VERIFY_WEBHOOK_SIGNATURES=true

IMAGE_GENERATION_COST=50.00
SEED_DEMO_USERS=false
```

When Render provides an internal PostgreSQL URL beginning with:

```text
postgresql://
```

the async SQLAlchemy application uses:

```text
postgresql+asyncpg://
```

Do not include the literal word `Key` in `FAL_KEY`. Store only the raw fal.ai API key.

Do not set `FAL_WEBHOOK_URL` on Render unless you intentionally want to override the automatic callback URL. The app can derive it from `RENDER_EXTERNAL_URL`.

On container start, Alembic applies the latest migration before Uvicorn starts.

After deployment, the API is available at a public Render URL such as:

```text
https://your-service.onrender.com
```

and the fal.ai callback resolves to:

```text
https://your-service.onrender.com/generate/image/callback
```

Swagger is available at:

```text
https://your-service.onrender.com/docs
```

## `pyproject.toml`

Production dependencies are defined under:

```toml
[project]
dependencies = [...]
```

Development-only dependencies are defined under:

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8.0,<9.0",
  "pytest-asyncio>=0.24,<1.0",
  "ruff>=0.8,<1.0",
]
```

The package discovery configuration installs only `app*` as the Python package and excludes migration/test directories from setuptools discovery:

```toml
[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["alembic*", "tests*"]
```

## Reviewer / demo usage

The deployed API keeps Swagger publicly available, but `POST /generate/image` is protected with a small demo key so random visitors cannot spend fal.ai credits.

Open the deployed service:

```text
https://YOUR-SERVICE.onrender.com/
```

The root redirects to Swagger:

```text
https://YOUR-SERVICE.onrender.com/docs
```

To run an image generation from Swagger:

1. Open `POST /generate/image`.
2. Click **Try it out**.
3. Enter the shared demo password in the `x-demo-key` header field.
4. Use a request body such as:

```json
{
  "user_id": "11111111-1111-1111-1111-111111111111",
  "prompt": "a red apple on a white table",
  "aspect_ratio": "1:1"
}
```

5. Click **Execute**.

A successful request is accepted with a response similar to:

```json
{
  "request_id": "fal-request-id",
  "status": "IN_QUEUE",
  "cost": "50.00"
}
```

The reviewer must obtain the demo key separately from the project owner. It is stored on Render as:

```text
DEMO_KEY=<shared-secret>
```

Do not commit the demo key to GitHub or place it in this README.

The same request can be sent outside Swagger with:

```bash
curl -X POST "https://YOUR-SERVICE.onrender.com/generate/image" \
  -H "Content-Type: application/json" \
  -H "X-Demo-Key: YOUR_DEMO_KEY" \
  -d '{
    "user_id": "11111111-1111-1111-1111-111111111111",
    "prompt": "a red apple on a white table",
    "aspect_ratio": "1:1"
  }'
```

The demo-key check protects only the generation route. The fal.ai callback remains publicly reachable because fal.ai must be able to deliver the webhook; callback authenticity is handled separately by fal webhook signature verification.

After submission, generation history can be checked with:

```text
GET /my-files/11111111-1111-1111-1111-111111111111
```

## Important production improvements

Before treating this as a full production payment/credit service:

- disable demo-user seeding;
- derive `user_id` from authenticated identity instead of trusting request JSON;
- add client-side request idempotency for `POST /generate/image`;
- add structured logging, metrics, and tracing;
- add reconciliation for orphan fal.ai requests;
- consider a wallet ledger instead of only a mutable balance;
- decide whether generated images should be copied into storage controlled by the service;
- add rate limiting;
- add product-specific prompt/content validation;
- add stronger operational monitoring around callback failures and retries.

## Status

The local API, Docker build/run flow, Alembic migrations, fake-fal test suite, wallet/refund logic, and callback idempotency flows have been validated locally.

The deployed public webhook path is intended to enable the final real end-to-end flow:

```text
Client
  ↓
Render FastAPI
  ↓
fal.ai
  ↓
Render public callback
  ↓
PostgreSQL job update / refund
```

A real fal.ai callback should be verified after deployment before considering the integration fully validated.
