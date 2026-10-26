# DeadlineGuard - combined frontend and backend

This package connects the React frontend and FastAPI backend supplied in your skill_lab folders. Your original files are unchanged. Read INTEGRATION_NOTES.md for the API fixes and remaining prototype limitations.

## Requirements

| | Windows | macOS |
|---|---|---|
| Python | 3.9 or newer (3.11+ recommended) | 3.9 or newer (3.11+ recommended) |
| Node.js | 20.19+ (or 22.12+ / 24) | 20.19+ (or 22.12+ / 24) |
| Terminal | PowerShell | Terminal (zsh) |

> **macOS:** check `python3 --version`. Python 3.9+ works, including the version that ships with macOS. If you prefer a newer release, install one with Homebrew (for example `brew install python@3.13`) and use `python3.13` instead of `python3` below.
>
> **Windows:** check `python --version`. If it is below 3.9, install Python 3.11+ and make sure `python` points to it. If `python` is older but the Python launcher is available, create the environment first with `py -3.11 -m venv .venv`; `setup.ps1` will reuse it.

Extract the ZIP fully before running anything, and run the commands from the extracted `DeadlineGuard-combined` folder.

## Quick start on Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Setup creates `.venv`, installs the Python and npm dependencies, and builds the frontend. Start runs one Python server for both the website and API. Open **http://127.0.0.1:8002**. API docs are at **http://127.0.0.1:8002/docs**. Use Ctrl+C in the terminal to stop.

The ZIP also includes the compiled frontend, so if you only want to run the built version you can install just Python dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

## Quick start on macOS

One-time setup:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
```

Start the server:

```bash
venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8002
```

Open **http://127.0.0.1:8002**. API docs are at **http://127.0.0.1:8002/docs**. Use Ctrl+C in the terminal to stop.

If the ZIP already contains a compiled frontend and you only want to run it, skip the `npm` commands and run the two Python steps above.

Do not run `setup.ps1` or `start.ps1` on macOS. They are PowerShell scripts for Windows.

## Accounts

| Role | Username | Password |
|---|---|---|
| Faculty | faculty1 | pass1234 |
| Student 1 | student1 | pass1234 |
| Student 2 | student2 | pass1234 |

Accounts and three clearly labeled demo assignments are seeded automatically on first launch. Passwords are PBKDF2 hashes in SQLite. These public credentials are for a local demonstration, not internet hosting. Login state is in memory, so sign in again after restarting.

## Upload / disconnect demonstration

1. Sign in as faculty1 and create a fresh assignment, with a deadline a few minutes ahead and a five-minute recovery window.
2. Sign in as student1. Open the assignment and download/select the provided 20 MiB sample.
3. Enable slow transfers and automatic disconnect after 12 MiB. Start uploading.
4. This backend uses **512 KiB chunks**: 20 MiB = **40 chunks**. At 12 MiB, 24 chunks are saved and 16 remain.
5. Reconnect, then Resume upload. Only the missing chunks are sent. Refreshing the page also preserves server progress; reselect the same PDF.
6. At 100%, the PDF is still **not submitted**. Click **Finalize submission** to verify it and generate the receipt.
7. Finalize after the deadline but within recovery to demonstrate a grace-recovered receipt. The server always enforces actual time; demo pacing cannot extend the deadline.

Switching off Wi-Fi does not interrupt localhost: the browser and server are on the same laptop. Use the explicitly labeled demo connection control for a reliable presentation. PDF samples contain an inert, labeled padding attachment so transfers are visible. The browser's progress is based on real server acknowledgments, not a timer.

## Development

Keep the backend running, then open another terminal in the project folder.

**Windows:**

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

**macOS:**

```bash
cd frontend
npm ci
npm run dev
```

Visit **http://127.0.0.1:5175**. Vite proxies `/api` to port 8002. Run the build command (`npm.cmd run build` on Windows, `npm run build` on macOS) after frontend edits, then restart the backend to serve the updated production build. The API and UI use the same origin/cookie; no manual CORS edits are needed.

## Tests and comparison

From the extracted project root:

**Windows:**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe backend/experiments/compare_limiters.py
```

**macOS:**

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python backend/experiments/compare_limiters.py
```

With Python 3.9, eight tests passed in integration validation. They use an isolated database and storage under `.test-runs`, not your demonstration data. The comparison page runs the supplied backend's deterministic limiter simulation; it is not a real HTTP load or latency benchmark.

## Troubleshooting

- **Python is older than 3.9:** install a newer version, for example `brew install python@3.13` on macOS or Python 3.11+ on Windows, and recreate `.venv`.
- **`setup.ps1` cannot be loaded on Windows:** run it with `powershell -ExecutionPolicy Bypass -File .\setup.ps1` as shown above.
- **Port 8002 is already in use:** stop the earlier Uvicorn process. This project uses port 8002 so it does not conflict with the earlier DeadlineGuard project on 8001. Use only one Uvicorn process.
- **`frontend/dist/index.html` is missing:** run the frontend build (`npm ci && npm run build` in `frontend/`) before starting the server.

## Files

- `backend/`: original backend structure plus contract serializers and integration fixes.
- `frontend/`: React source, npm lockfile, compiled dist, Vite proxy configuration.
- `samples/`: 5/20 MiB readable PDFs with test padding, hashes and previews.
- `scripts/make_demo_pdfs.py`: optional sample regeneration (requires reportlab and pypdf).
- `setup.ps1` / `start.ps1`: Windows setup and launch commands. macOS uses the commands in this README.
- `INTEGRATION_NOTES.md`: changes and limits; supersedes outdated details in supplied teaching documents.
- `VALIDATION.md`: recorded checks and verification boundaries.

Runtime data is created under `data/`. No preexisting database, login tokens, real submissions, node_modules or Python environment is included. The supplied database was intentionally not reused: the combined schema adds course data and starts with fresh demo records. See INTEGRATION_NOTES.md before attempting any migration.
