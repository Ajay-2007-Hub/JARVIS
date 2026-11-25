# JARVIS

A local AI assistant project with a FastAPI backend and a React frontend.
The backend binds to `127.0.0.1`; it is not exposed to the network.

## Run

Create the Python 3.11 environment and install the pinned backend dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Build the frontend and start the backend:

```powershell
Push-Location frontend
npm install
npm run build
Pop-Location
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The `/health` endpoint reports backend and Ollama
status. Ollama configuration is read from `.env` (`OLLAMA_URL` and
`OLLAMA_MODEL`).

## Auto-start

Run `scripts\launcher.py` manually with the virtual environment to start the
local backend, model warm-up, browser window, and tray icon. The Settings panel
can request auto-start changes; those changes take effect only after approval.
For manual Task Scheduler registration, run
`scripts\register_autostart.ps1` in the current user's session. See
[docs/STARTUP.md](docs/STARTUP.md) for enabling, disabling, troubleshooting,
and the reboot test checklist.
