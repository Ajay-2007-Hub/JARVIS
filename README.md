# JARVIS

A local AI assistant project with a FastAPI backend and a React frontend.

## Development

Create and activate a Python virtual environment, then install the backend dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The API health check is available at `http://127.0.0.1:8000/health`.

To run the frontend in development mode:

```powershell
cd frontend
npm install
npm run dev
```
