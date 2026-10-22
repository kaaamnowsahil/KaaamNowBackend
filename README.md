# KaaamNow Backend

REST API for **KaaamNow**, a shift-staffing marketplace that connects businesses with workers for short shifts.

Built with **FastAPI**, **asyncpg** and **PostgreSQL**. Deployed on **Vercel** (region `sin1`).

## Requirements

- Python 3.12+ (the repo pins 3.14 in `.python-version`)
- PostgreSQL 14+
- A Firebase project with Phone sign-in enabled (for OTP)

## Quick start

```bash
make install            # creates .venv and installs requirements-dev.txt
# create .env.dev with the settings below
make run-api ENV=dev    # starts the API on http://localhost:8000
```

On startup the server applies every SQL file in `sql/` (tables, then relations) and runs `sql/seed/seed.sql`. Both are idempotent, so restarting is always safe. With `DB_AUTO_CREATE=true` the database itself is created if it is missing.

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Environment profiles

Settings are read from `.env.<profile>`. All `.env.*` files are gitignored, and every setting has a default in `app/config/settings.py`.

| Profile | File | Select with |
|---|---|---|
| dev (default) | `.env.dev` | `make run-api ENV=dev` |
| prod | `.env.prod` | `make run-api ENV=prod` |

Key settings:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://...`) |
| `JWT_SECRET_KEY` | Signs access/refresh tokens (32+ characters in prod) |
| `OTP_PROVIDER` | `firebase` (real SMS via Firebase) or `console` (dev only, logs the code) |
| `FIREBASE_PROJECT_ID` | Firebase project used to verify phone ID tokens |
| `CORS_ORIGIN` | Allowed origins (`*` is refused in prod) |
| `PAYMENT_PROVIDER`, `PAYOUT_PROVIDER`, `PUSH_PROVIDER` | `fake` / `console` providers until real ones are integrated |

## Phone sign-in (Firebase)

The backend never sends SMS when `OTP_PROVIDER=firebase`. The client does:

1. Call Firebase `signInWithPhoneNumber(phone)`; Firebase sends the SMS.
2. Call `confirm(code)` and then `getIdToken()`.
3. Send the token as `id_token` to `POST /api/v1/auth/signup` or `POST /api/v1/auth/firebase/verify`.

The backend verifies the token against Google's signing keys and returns KaaamNow access and refresh tokens. `POST /api/v1/auth/otp/send` only works with the `console` provider.

## API overview

All routes live under `/api/v1`. The full contract is in [`openapi.yaml`](openapi.yaml).

| Group | Prefix | Notes |
|---|---|---|
| Auth | `/auth` | Signup, Firebase verify, password login, refresh |
| Me | `/me` | Current user |
| Catalog | `/catalog` | Languages, rating tags, payment methods, fee policy |
| Work categories | `/work-categories` | Public GET, admin POST / PATCH / DELETE |
| Business types | `/business-types` | Public GET, admin POST / PATCH / DELETE |
| Business | `/business` | Business profile and shifts |
| Worker / Workers | `/worker`, `/workers` | Worker profile, shift feed, public worker profiles |
| Assignments | `/assignments` | Applications, attendance, chat |
| Payments | `/payments` | Invoices and payment webhooks |
| Notifications | `/notifications` | In-app notifications |
| Content / Support | `/content`, `/support` | Terms, FAQs, support tickets |
| Admin | `/admin` | Verification, generic CRUD, metrics |

## Common commands

```bash
make run-api ENV=dev   # run the API
make test              # pytest (integration tests need a reachable dev database)
make lint              # ruff check + format check
make format            # auto-fix lint and formatting
make openapi           # regenerate openapi.yaml
```

## Project layout

```
app/
  routes/        HTTP routers (one folder per domain)
  services/      business logic
  repositories/  asyncpg queries
  schemas/       Pydantic request/response models
  constants/     paths, messages and other constants
  config/        settings and env profile loading
  db/            connection pool and schema bootstrap
  security/      JWT, permissions, password hashing
sql/
  tables/        one file per table
  relations/     foreign keys
  seed/          reference data (languages, work categories, business types, ...)
scripts/         run.py (entrypoint), export_openapi.py
tests/           unit and integration tests
index.py         Vercel entrypoint
```

## Deployment

Vercel uses `index.py` as the entrypoint (see `vercel.json`). Set the prod environment variables in the Vercel project; the schema and seed are applied on cold start.

## Branches

- `dev`: integration branch, where feature branches are merged.
- `main`: production.
