# FastAPI + fal.ai Image Generation

A production-minded FastAPI example for asynchronous image generation with fal.ai, SQLAlchemy credits, webhooks, and idempotent refunds.

The code is intentionally organized with the same mental model commonly used in NestJS projects:

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
  - submits `fal-ai/nano-banana` asynchronously;
  - uses a webhook instead of polling;
  - stores a `GenerationJob` in `IN_QUEUE`.
- `POST /generate/image/callback`
  - optionally verifies the fal webhook signature;
  - marks a job `SUCCESS` and stores the generated URL;
  - marks a failed job `FAILED` and refunds exactly once;
  - safely handles duplicate/concurrent callbacks.
- `GET /my-files/{user_id}`
  - returns the user's balance and generation history.
- demo users `1` and `2` with configurable initial balance.
- SQLite for local development and PostgreSQL support for production.
- `fal-client==0.8.0` isolated behind an application port.

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
```

### `controllers/`

The HTTP layer.

It owns:

- FastAPI routers;
- HTTP request/response schemas;
- dependency extraction from `app.state`;
- webhook HTTP validation;
- application-exception → HTTP-response mapping.

Controllers should not contain wallet or generation business logic.

### `application/`

The business/application layer.

`GenerationService` knows the workflow:

1. debit the user;
2. submit the request to fal;
3. create the generation job;
4. process callback success/failure;
5. request exactly-once refund behavior.

It does **not** import FastAPI, SQLAlchemy, `fal_client`, `httpx`, or PyNaCl.

`ports.py` defines the interfaces the application requires from infrastructure:

- `FalGateway`
- `GenerationUnitOfWork`
- `GenerationUnitOfWorkFactory`

### `infrastructure/`

Everything that talks to external technology.

`database/` contains SQLAlchemy models, engine/session setup, and the concrete unit-of-work implementation.

`fal/` contains the `fal_client` adapter and fal webhook verification/parsing.

This means the application depends on abstractions while infrastructure implements those abstractions.

## API

### `POST /generate/image`

Request:

```json
{
  "user_id": 1,
  "prompt": "image of cat with big ears",
  "aspect_ratio": "1:1"
}
```

Successful response (`202 Accepted`):

```json
{
  "request_id": "fal-request-id",
  "status": "IN_QUEUE",
  "cost": "50.00"
}
```

If the user does not exist, the application raises `UserNotFoundError` and the global FastAPI exception handler returns `404`.

If the user does not have enough balance, it returns `400` and no money is deducted.

If fal submission raises, `FalSubmissionError` leaves the unit of work with an exception, so the database transaction rolls the debit back and the API returns `502`.

### `POST /generate/image/callback`

Success payload example:

```json
{
  "request_id": "fal-request-id",
  "gateway_request_id": "fal-request-id",
  "status": "OK",
  "payload": {
    "images": [
      {
        "url": "https://cdn.example/image.png",
        "content_type": "image/png"
      }
    ]
  }
}
```

The job becomes `SUCCESS` and the first image URL is stored in `request_url`.

Failure example:

```json
{
  "request_id": "fal-request-id",
  "status": "ERROR",
  "error": "generation failed",
  "payload": null
}
```

The job becomes `FAILED`, `is_refunded=true`, and the original job cost is added back to the wallet.

### `GET /my-files/{user_id}`

Returns:

- `user_id`
- current `ai_balance`
- generation jobs ordered newest first

## Why callbacks are idempotent

Checking a job in Python and then updating it is not enough:

```python
if job.status == IN_QUEUE:
    job.status = FAILED
    user.ai_balance += job.cost
```

Two webhook requests could both read `IN_QUEUE` before either transaction commits and both refund the wallet.

The SQLAlchemy infrastructure instead performs a conditional update:

```sql
UPDATE generation_jobs
SET status = 'FAILED', is_refunded = true
WHERE request_id = :request_id
  AND status = 'IN_QUEUE'
  AND is_refunded = false;
```

Only one transaction can claim that transition.

The winning transaction then increments the wallet in the **same database transaction**. A duplicate callback sees a terminal job and returns `already_processed` without changing balance.

Success uses the same `status = IN_QUEUE` claim pattern.

`request_id` also has a unique database constraint.

## Balance handling

Wallet values use SQL `NUMERIC(12, 2)` / Python `Decimal`, not binary `float`.

The debit is atomic:

```sql
UPDATE users
SET ai_balance = ai_balance - :cost
WHERE id = :user_id
  AND ai_balance >= :cost;
```

This prevents two concurrent generation requests from both spending the same balance.

The fal queue submission occurs while the SQL unit of work is open. If fal submission fails, leaving the unit of work with an exception rolls the debit back.

### Distributed transaction trade-off

Your SQL database and fal's remote queue cannot participate in one atomic transaction.

A rare crash after fal accepts the remote request but before the local SQL commit can create an orphan fal request. In this design the user is not charged, but the service owner could pay for that orphan request.

For a larger financial system, use a wallet ledger plus an outbox/saga/reconciliation workflow.

## Why the exception handlers live in `controllers/`

Exceptions such as:

- `UserNotFoundError`
- `InsufficientBalanceError`
- `FalSubmissionError`
- `GenerationJobNotFoundError`

are application errors.

How they become `404`, `400`, or `502` is an HTTP concern, so that mapping belongs in the controller layer rather than inside `GenerationService`.

Webhook-specific HTTP failures such as invalid signatures or malformed request bodies stay directly in the webhook controller because they are transport/security validation, not application business errors.

## Configuration

Copy `.env.example` to `.env` and set at least your fal key/environment as needed.

Important settings include:

```env
DATABASE_URL=sqlite+aiosqlite:///./app.db
FAL_MODEL=fal-ai/nano-banana
FAL_WEBHOOK_URL=https://your-public-host/generate/image/callback
FAL_VERIFY_WEBHOOK_SIGNATURES=true
IMAGE_GENERATION_COST=50.00
SEED_DEMO_USERS=true
DEMO_USER_BALANCE=1000.00
```

fal must be able to reach the callback URL, so `localhost` will not work for real webhook delivery. Use a public HTTPS endpoint/tunnel while developing locally.

## Local setup

Python 3.11+:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run:

```powershell
uvicorn app.main:app --reload
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## Tests

```bash
python -m pytest -q
```

The tests use a fake implementation of the `FalGateway` application port, so no real fal credits are spent.

They cover:

- successful debit and queue creation;
- unknown user;
- insufficient balance;
- rollback when fal submission fails;
- success callback;
- duplicate success callback;
- failed callback with exactly one refund;
- concurrent duplicate failure callbacks;
- unknown callback request ID.

## Production improvements

Before using this as a real payment/credit service:

- use Alembic migrations instead of `create_all`;
- use PostgreSQL;
- disable demo-user seeding;
- derive `user_id` from authentication instead of trusting request JSON;
- add an `Idempotency-Key` to `POST /generate/image` so client retries cannot create two paid jobs;
- add structured logging, metrics, and tracing;
- add reconciliation for orphan remote fal requests;
- consider a wallet ledger instead of storing only a mutable balance;
- decide whether generated images should be copied into storage you control;
- add rate limits and product-specific prompt/content validation.
