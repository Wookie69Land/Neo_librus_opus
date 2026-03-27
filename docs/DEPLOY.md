# Librarius — Production Deployment Guide

## 1. Connect to the server

```bash
ssh lukasz@nanys.pl -p 93
```

---

## 2. Find or recreate the app directory

```bash
# Search for the old folder
find ~ /srv /opt /var -name "Librarius" -type d 2>/dev/null

# Or look for any git repo
find ~ /srv /opt -name ".git" -type d 2>/dev/null | xargs -I{} dirname {}
```

If found, jump into it and check its state:

```bash
cd ~/Librarius
git status
git log --oneline -5
git pull
```

### Starting from scratch (if folder is gone)

```bash
rm -rf ~/Librarius   # only if it exists but is broken
git clone <your-repo-url> Librarius
cd ~/Librarius
```

---

## 3. Prepare the `.env` file

The app reads `.env` from the project root. **Never commit this file.**

### Option A — Copy from your local machine (run on your PC, not on the server)

```bash
scp -P 93 "c:\Users\lukas\Jack_a_dull_boy\OKNO_PW\Projekt grupowy\main_app\.env" lukasz@nanys.pl:~/Librarius/.env
```

### Option B — Create it manually on the server

```bash
nano ~/Librarius/.env
```

Minimum required contents:

```env
SECRET_KEY=your-very-long-random-secret-key-here
DEBUG=False
ALLOWED_HOSTS=librarius-api.nanys.pl,localhost,127.0.0.1

# This is the only password Docker Compose cannot hardcode safely
MYSQL_PASSWORD=your_mysql_password_here

# Recommended for cyclic Google Books enrichment
GOOGLE_BOOKS_API_KEY=your_google_books_api_key_here
GOOGLE_BOOKS_TIMEOUT=15
CYCLIC_TASK_REPORT_RETENTION=3

# Optional override for the frontend redirect after account activation
ACCOUNT_ACTIVATION_SUCCESS_URL=https://librarius.nanys.pl/register-success
```

> `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_HOST`, `MYSQL_PORT` are already hardcoded
> in `docker-compose.prod.yml` — you don't need to repeat them in `.env`.

Verify the file:

```bash
cat ~/Librarius/.env
```

---

## 4. Ensure Docker is running

```bash
docker info
sudo systemctl start docker   # if not running
```

---

## 5. Deploy from scratch

```bash
cd ~/Librarius

# Tear down any old containers, networks, volumes and images
docker compose -f docker-compose.prod.yml down --volumes --rmi all

# Build a fresh image and start in the background
docker compose -f docker-compose.prod.yml up --build -d
```

Migrations run automatically on startup (the container command is
`python manage.py migrate && python manage.py collectstatic --noinput && python manage.py runserver 0.0.0.0:8000`).

---

## 6. Watch the startup logs

```bash
docker compose -f docker-compose.prod.yml logs -f
```

You should see:

```
web-1  | Operations to perform: Apply all migrations...
web-1  | Running migrations: No migrations to apply.
web-1  | Starting development server at http://0.0.0.0:8000/
worker-1 | Starting worker for 4 functions: cyclic_book_seeder, cyclic_book_manager, ...
```

Press `Ctrl+C` to stop following (the container keeps running).

---

## 7. Check container status

```bash
docker compose -f docker-compose.prod.yml ps
```

The `web` service must show `Up`.

The `worker` and `redis` services should also show `Up`.

---

## 8. Create a Django superuser (first deploy only)

### Option A — Interactive prompt

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Follow the prompts to enter a username, e-mail, and password.

### Option B — Django shell (non-interactive / scripted)

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell
```

Then inside the shell:

```python
from app.domain.models import LibraryUser

LibraryUser.objects.create_superuser(
    username="admin",
    email="admin@example.com",
    password="YourStrongPassword123!",
)
exit()
```

Or as a one-liner (useful in CI/CD or automated provisioning):

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell -c "
from app.domain.models import LibraryUser
LibraryUser.objects.create_superuser('admin', 'admin@example.com', 'YourStrongPassword123!')
"
```

> The superuser account is created with `is_active=True` and `is_staff=True` automatically.

---

## 9. Update after a code change

```bash
cd ~/Librarius
git pull
docker compose -f docker-compose.prod.yml up --build -d
```

---

## 10. Useful maintenance commands

```bash
# Tail live logs
docker compose -f docker-compose.prod.yml logs -f web

# Tail worker logs for cyclic jobs
docker compose -f docker-compose.prod.yml logs -f worker

# Run any management command inside the container
docker compose -f docker-compose.prod.yml exec web python manage.py <command>

# Stop everything
docker compose -f docker-compose.prod.yml down
```

### Running `manage.py` commands inside the container

Use this pattern:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py <command>
```

Equivalent patterns by environment:

```bash
# Local virtual environment
python manage.py <command>

# Local Docker / dev compose
docker compose exec web python manage.py <command>

# Production Docker
docker compose -f docker-compose.prod.yml exec web python manage.py <command>
```

Examples:

```bash
# Apply migrations manually
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Rebuild collected static files manually
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput

# Open Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Create a superuser
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# Run the ISBN import command
docker compose -f docker-compose.prod.yml exec web python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl

# Seed curated top 100 Polish books and authors
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_books

# Reseed the curated top 100 Polish books from scratch
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_books --replace-curated

# Seed 10 major Polish libraries
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_libraries

# Reseed the curated libraries from scratch
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_libraries --replace-seeded
```

### Domain management commands in local development and Docker

Commands currently available in `app/domain/management/commands`:

- `clear_books_data`
- `fetch_isbn_books`
- `run_cyclic_task`
- `seed_polish_books`
- `seed_polish_libraries`
- `show_cyclic_task_reports`

#### Local virtual environment

```bash
python manage.py clear_books_data --force
python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl
python manage.py seed_polish_books
python manage.py seed_polish_books --replace-curated
python manage.py seed_polish_libraries
python manage.py seed_polish_libraries --replace-seeded
python manage.py run_cyclic_task cyclic_book_seeder
python manage.py show_cyclic_task_reports --task cyclic_book_manager
```

#### Local Docker / dev compose

```bash
docker compose exec web python manage.py clear_books_data --force
docker compose exec web python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl
docker compose exec web python manage.py seed_polish_books
docker compose exec web python manage.py seed_polish_books --replace-curated
docker compose exec web python manage.py seed_polish_libraries
docker compose exec web python manage.py seed_polish_libraries --replace-seeded
docker compose exec web python manage.py run_cyclic_task cyclic_book_seeder
docker compose exec web python manage.py show_cyclic_task_reports --task cyclic_book_manager
```

#### Production Docker

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py clear_books_data --force
docker compose -f docker-compose.prod.yml exec web python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_books
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_books --replace-curated
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_libraries
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_libraries --replace-seeded
docker compose -f docker-compose.prod.yml exec web python manage.py run_cyclic_task cyclic_book_seeder
docker compose -f docker-compose.prod.yml exec web python manage.py show_cyclic_task_reports --task cyclic_book_manager
```

### Seeding reference data in production

Recommended order:

```bash
# Optional: clear imported or test books before loading curated data
docker compose -f docker-compose.prod.yml exec web python manage.py clear_books_data --force

# Seed curated books and authors
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_books

# Seed curated libraries
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_libraries
```

The seeding commands are idempotent. To rebuild only curated records, use:

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_books --replace-curated
docker compose -f docker-compose.prod.yml exec web python manage.py seed_polish_libraries --replace-seeded
```

### Cyclic background jobs

The project uses `arq` with Redis for scheduled background work. The worker runs in a
separate `worker` container and uses the `Europe/Warsaw` timezone.

Configured daily jobs:

```text
07:00  cyclic_book_seeder
07:15  cyclic_book_manager
```

#### `cyclic_book_seeder`

- Runs the equivalent of:
  `python manage.py fetch_isbn_books --limit 250 --batch-size 10 --no-verify-ssl`
- Safety condition: if the database already contains more than `5000` books, the job
  skips synchronization for that day.
- Every run stores a report in the database. Only the latest `3` reports are kept
  per task by default.

#### `cyclic_book_manager`

Runs two maintenance steps every day:

- `book_enricher`
  Selects up to `100` books with missing metadata and queries Google Books using a
  generic API client. It fills or improves:
  - cover image (`cover_url`)
  - categories (`category`, appended without duplicates)
  - Google volume ID (`google_id`)
  - authors, but only in conservative correction scenarios
  The job marks each processed book with `google_checked = true`, so the same
  book is not sent to Google Books repeatedly on later daily runs.

- library assignment step
  Finds books assigned to fewer than `2` libraries and randomly adds them to enough
  libraries to reach between `2` and `5` total assignments.

#### First production evidence when jobs seem to run only once

If the worker starts correctly, but later reports show only one automatic run and then
silence, collect these three signals first:

```bash
# 1. Worker startup log
docker compose -f docker-compose.prod.yml logs --tail=1500 worker

# 2. Cron jobs known to the worker
docker compose -f docker-compose.prod.yml exec worker python -c "from app.tasks.worker import WorkerSettings; print([c.name for c in WorkerSettings.cron_jobs])"

# 3. Reports written by the scheduled jobs
docker compose -f docker-compose.prod.yml exec web python manage.py show_cyclic_task_reports --task cyclic_book_seeder --limit 10
docker compose -f docker-compose.prod.yml exec web python manage.py show_cyclic_task_reports --task cyclic_book_manager --limit 10
```

Example interpretation from a real production check:

- `logs worker` showed only worker startup:
  `Starting worker for 4 functions: cyclic_book_seeder, cyclic_book_manager, book_enricher, assign_books_to_random_libraries`
- `WorkerSettings.cron_jobs` returned:
  `['cyclic_book_seeder', 'cyclic_book_manager']`
- `show_cyclic_task_reports` showed the last automatic runs at:
  - `2026-03-22T07:00:00+00:00` for `cyclic_book_seeder`
  - `2026-03-22T07:15:00+00:00` for `cyclic_book_manager`
- Older rows with `2026-03-21T16:xx:xx+00:00` were manual runs triggered with
  `run_cyclic_task`, not scheduler runs.

What this means:

- the worker process starts successfully
- the worker imports and registers both cron jobs correctly
- the report command works correctly and shows real executions
- if no newer automatic rows appear, the scheduler did not fire again after that day

In practice this usually means one of these operational problems:

- the `worker` container was down during the next scheduled window
- the `worker` container restarted after `07:15`, so the next cron run moved to the next day
- the server time or container timezone was different from what you expected
- the worker lost Redis connectivity or was recreated during the day

Important: `show_cyclic_task_reports` does not calculate the schedule. It only prints
rows already saved to the database. If there is no new row, the job did not actually run.

#### Manual testing right now

You can run any cyclic job immediately from Django without waiting for cron:

```bash
# Run the daily seeder now
docker compose -f docker-compose.prod.yml exec web python manage.py run_cyclic_task cyclic_book_seeder

# Run the daily manager now
docker compose -f docker-compose.prod.yml exec web python manage.py run_cyclic_task cyclic_book_manager

# Run only Google Books enrichment
docker compose -f docker-compose.prod.yml exec web python manage.py run_cyclic_task book_enricher

# Run only random library assignment
docker compose -f docker-compose.prod.yml exec web python manage.py run_cyclic_task assign_books_to_random_libraries

# Show the last reports for a task
docker compose -f docker-compose.prod.yml exec web python manage.py show_cyclic_task_reports --task cyclic_book_manager
```

Recent `book_enricher` reports include:

- `examined`: how many books consumed one API attempt in that run
- `no_match`: Google Books returned no acceptable volume for those books
- `unchanged`: a match existed but did not improve stored metadata
- `temporary_failures`: books deferred because Google Books returned retryable errors such as `429`
- `samples`: a small sample of book IDs/titles from each outcome bucket

Recent `library_assignment` reports include `assignment_samples`, which show a
small sample of books and the library IDs added during that manager run.

The same commands work locally if you replace `docker-compose.prod.yml` with the
local compose file or run them directly from your local virtual environment.

#### Task debugging

When cyclic jobs stop appearing for a few days, collect the container lifecycle,
worker logs, Redis logs, and timezone signals together:

```bash
# Show all container states, including exited ones
docker compose -f docker-compose.prod.yml ps -a

# Inspect the worker container start time, restart count, and current state
docker inspect $(docker compose -f docker-compose.prod.yml ps -q worker) --format '{{.State.StartedAt}} restart={{.RestartCount}} status={{.State.Status}}'

# Worker logs since the first missing day
docker compose -f docker-compose.prod.yml logs --since "2026-03-22T00:00:00" worker

# Redis logs from the same period
docker compose -f docker-compose.prod.yml logs --since "2026-03-22T00:00:00" redis

# Host time and timezone
date
timedatectl

# Worker container time and timezone
docker compose -f docker-compose.prod.yml exec worker date
docker compose -f docker-compose.prod.yml exec worker env | grep '^TZ='
```

#### Google Books API quota

The enrichment code supports API key authentication via `GOOGLE_BOOKS_API_KEY`.
To raise practical request limits, configure the Books API in Google Cloud and attach
the key in `.env`.

Reference:

```text
https://developers.google.com/books/docs/v1/using
```

---

## Checking if a browser is available over SSH

You almost certainly have no GUI browser on the server, but you have several options:

### Option A — Use the interactive API docs from your local machine

The API ships with built-in Swagger UI. Just open in your browser:

```
https://librarius-api.nanys.pl/api/docs
```

### Option B — w3m / lynx (text-mode browser on the server)

```bash
# Check if one is installed
which w3m lynx

# Install if missing (Debian/Ubuntu)
sudo apt install w3m

# Then open the docs
w3m https://librarius-api.nanys.pl/api/docs
```

### Option C — SSH port forwarding (forward remote port to your local browser)

Open a second terminal on your local machine and run:

```bash
ssh lukasz@nanys.pl -p 93 -L 8080:localhost:8001
```

Then open **http://localhost:8080/api/docs** in your local browser.
Everything is routed through the SSH tunnel — no need for a server-side browser.

---

## Testing: Full register → activate → login → logout flow

All examples use `curl`. Replace `TOKEN` with the value returned by `/api/auth/login`.

> **Base URL:** `https://librarius-api.nanys.pl`
>
> **Note:** Django Ninja does **not** use trailing slashes — append none.

---

### Step 1 — Register a new user

Password requirements:

- minimum 12 characters
- at least one uppercase letter
- at least one digit
- at least one special character
- cannot be empty or whitespace only

```bash
curl -s -X POST https://librarius-api.nanys.pl/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "StrongPass123!",
    "first_name": "Jan",
    "last_name": "Kowalski",
    "region": 7
  }'
```

Expected response (`201`):

```json
{
  "id": 2,
  "username": "jkowalski",
  "email": "test@example.com",
  "first_name": "Jan",
  "last_name": "Kowalski",
  "region": 7,
  "is_active": false,
  "date_joined": "...",
  "last_login": null
}
```

An activation e-mail is sent to the provided address. If you don't have e-mail
configured, activate manually (see Step 2b).

---

### Step 2a — Activate via the e-mail link

Open the link from the e-mail in a browser. It looks like:

```
https://librarius-api.nanys.pl/api/auth/activate?uid=<uid>&token=<token>
```

Expected behavior:

1. the backend returns HTTP `302`
2. the browser is redirected to:

```text
https://librarius.nanys.pl/register-success
```

If you override `ACCOUNT_ACTIVATION_SUCCESS_URL` in `.env`, the redirect target changes accordingly.

---

### Step 2b — Activate manually (when e-mail is not configured)

```bash
# Get into the container shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Then in the Django shell:
from app.domain.models import LibraryUser
u = LibraryUser.objects.get(email="test@example.com")
u.is_active = True
u.save()
exit()
```

---

### Step 3 — Login

The `login` field accepts either a **username** or an **e-mail address**.

```bash
curl -s -X POST https://librarius-api.nanys.pl/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login": "jkowalski", "password": "StrongPass123!"}'
```

Or with e-mail:

```bash
curl -s -X POST https://librarius-api.nanys.pl/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login": "test@example.com", "password": "StrongPass123!"}'
```

Expected response (`200`):

```json
{"token": "<signed_jwt_token>"}
```

Save the token — you need it for all authenticated requests.

---

### Step 4 — Test an authenticated endpoint

```bash
curl -s https://librarius-api.nanys.pl/api/users/2 \
  -H "Authorization: Bearer <signed_jwt_token>"
```

---

### Step 5 — Logout

```bash
curl -s -X POST https://librarius-api.nanys.pl/api/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"token": "<signed_jwt_token>"}'
```

Expected response (`200`):

```json
{"detail": "Logout successful"}
```

---

### Quick smoke test (admin account, already active)

If you created a superuser in Step 8 of the deployment:

```bash
# Login
TOKEN=$(curl -s -X POST https://librarius-api.nanys.pl/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login": "admin", "password": "YourStrongPassword123!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "Token: $TOKEN"

# Hit a protected endpoint
curl -s https://librarius-api.nanys.pl/api/users/1 \
  -H "Authorization: Bearer $TOKEN"

# Swagger UI
curl -s https://librarius-api.nanys.pl/api/docs | head -20
```

---

### Common error responses

| Error | Cause | Fix |
|---|---|---|
| `{"detail": [{"type": "missing", "loc": [..., "login"], ...}]}` | Sent `username` instead of `login` | Use `"login"` as the key |
| `{"detail": "Account not activated"}` | `is_active = False` | Complete e-mail activation or use Step 2b |
| `{"detail": "Invalid credentials"}` | Wrong username/password | Check credentials |
| `{"detail": ["This password must contain at least one uppercase letter.", ...]}` | Password does not meet security policy | Use a 12+ char password with uppercase, digit, and special character |
| `{"detail": [{"type": "value_error", ... "Enter a valid email address." ...}]}` | Invalid e-mail format | Send a valid e-mail, e.g. `user@example.com` |
| `{"detail": [{"type": "value_error", ... "First name contains unsupported characters." ...}]}` | Invalid `first_name` or `last_name` | Use only letters, spaces, apostrophes, and hyphens |
| `500 Server Error` | Unhandled exception | Check logs: `docker compose -f docker-compose.prod.yml logs -f web` |
