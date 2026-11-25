# JARVIS startup

## Startup flow

```text
Windows user signs in
  -> JARVIS scheduled task starts scripts/launcher.py with .venv pythonw.exe
  -> launcher opens the existing UI if the local backend already responds
  -> otherwise launcher starts Ollama if needed, waits for it, and warms the model
  -> launcher starts Uvicorn on 127.0.0.1:8000 and waits for /health
  -> launcher opens Edge app mode (or the default browser) and starts the tray icon
  -> launcher supervises the backend and retries up to three times after a failure
```

The model warm-up is skipped when the battery is below 20% and unplugged. The
backend remains bound to loopback only. Auto-start changes requested from the
Settings panel create a 60-second approval request; the Task Scheduler script
does not run until that request is approved.

## Run the launcher manually

From the project root, run:

```powershell
.\.venv\Scripts\python.exe .\scripts\launcher.py
```

Build the frontend first with `npm run build` in `frontend/` if you want the
backend to serve the UI. The launcher uses the project root derived from its
own script location; paths passed to Windows processes are separate arguments,
so spaces in the project path are supported.

## Enable or disable auto-start

You can change the setting in the JARVIS Settings panel. The requested change
appears in Pending approvals and must be approved before Windows settings are
modified. To enable or disable manually, run the corresponding script from the
current user's PowerShell session (do not run as administrator):

```powershell
.\scripts\register_autostart.ps1
.\scripts\unregister_autostart.ps1
.\scripts\status_autostart.ps1
```

The registration script creates a `JARVIS` task for the current user's
interactive logon, delayed by 30 seconds. It runs with limited privileges,
continues on battery, and retries task failures. Registration is intentionally
not performed automatically by the app setup or tests.

## Logs

Backend, launcher, tray, and approval activity is written to
`logs\jarvis.log`. The file rotates at approximately 1 MB and retains three
backups (`jarvis.log.1`, etc.). Inspect the newest entries after a failed
startup or approval. Log files are local and ignored by Git.

## Troubleshooting

- **Task runs but no UI:** Confirm the task is configured for interactive
  logon, the user is signed in, `frontend\dist` exists, and the task's working
  directory points to this project root. Check `logs\jarvis.log` and the task's
  last run result with `scripts\status_autostart.ps1`.
- **Ollama not found:** Ensure Ollama is installed and available on `PATH`, or
  installed in `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. Check that the
  Ollama service can bind to `127.0.0.1:11434`.
- **Slow first reply:** The launcher warms the configured `OLLAMA_MODEL` before
  starting the UI, unless the battery is below 20% and unplugged. Confirm the
  model exists in Ollama and review the log for warm-up errors.
- **Project path contains spaces:** Keep the project directory stable and use
  the provided scripts. They derive paths from their own locations and pass
  executable arguments as lists or separately quoted PowerShell arguments.
- **Backend health reports Ollama offline:** Check `OLLAMA_URL` in `.env`
  (default `http://127.0.0.1:11434`) and open `/health` again.

## Manual test checklist

- [ ] Run `scripts\launcher.py` by hand; confirm the browser window and tray icon appear.
- [ ] After registering the task, run `Start-ScheduledTask -TaskName JARVIS` and inspect `Get-ScheduledTaskInfo -TaskName JARVIS`.
- [ ] Sign out and back in; confirm the UI opens.
- [ ] Reboot the computer; confirm the task starts after sign-in.
- [ ] Stop Ollama and relaunch JARVIS; confirm Ollama is started or a clear log error is written.
- [ ] Launch JARVIS twice quickly; confirm the existing backend is reused.
- [ ] Unplug the charger with battery below 20%; confirm model warm-up is skipped.
- [ ] Read `logs\jarvis.log` after each check.
