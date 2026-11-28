# Urban Air Quality Assistant

The Urban Air Quality Assistant is a React and FastAPI application for exploring modelled outdoor air quality and receiving household-specific indoor guidance and practical chat responses.

## Features

- City search and location selection
- Open-Meteo current pollutant readings and hourly PM2.5 data
- Outdoor family recommendations
- Household purifier and cooking-fuel preferences
- Indoor-air advice
- Local Qwen chat through Ollama
- Conversation history limited to the current city/session context

## Architecture

- `frontend/`: React, TypeScript, and Vite user interface
- `backend/main.py`: FastAPI application and API endpoints
- `backend/tests/`: Backend unit and integration-style request tests
- Ollama runs locally and provides the `qwen3:4b` chat model
- Open-Meteo provides external location and air-quality data

## Technology stack

- React 19
- TypeScript
- Vite
- FastAPI
- Pydantic
- HTTPX
- Ollama Python package
- Ollama with `qwen3:4b`

## Prerequisites

- Python 3.12 or a compatible Python 3 runtime
- Node.js 22 or a compatible Node.js runtime
- npm
- Ollama installed and running locally
- Internet access for Open-Meteo requests

## Backend setup

```powershell
cd urban-air-quality-assistant/backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Start the API:

```powershell
python main.py
```

The default API URL is `http://127.0.0.1:8000`.

## Frontend setup

```powershell
cd urban-air-quality-assistant/frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

The Vite frontend defaults to `http://localhost:5173`.

## Ollama setup

Install and start Ollama, then pull the required model:

```powershell
ollama pull qwen3:4b
ollama serve
```

Keep Ollama running while using `/api/chat`.

## Environment variables

Backend variables are documented in `backend/.env.example`:

- `BACKEND_HOST`: FastAPI bind host
- `BACKEND_PORT`: FastAPI bind port
- `CORS_ORIGINS`: comma-separated allowed frontend origins
- `OLLAMA_HOST`: local Ollama base URL
- `OLLAMA_MODEL`: Ollama model name
- `OLLAMA_TIMEOUT_SECONDS`: Ollama request timeout
- `AIR_QUALITY_URL`: Open-Meteo air-quality endpoint
- `AIR_QUALITY_TIMEOUT_SECONDS`: air-quality request timeout
- `LOCATION_URL`: Open-Meteo geocoding endpoint
- `LOCATION_TIMEOUT_SECONDS`: location-request timeout

Frontend variables are documented in `frontend/.env.example`:

- `VITE_API_BASE_URL`: FastAPI base URL

Frontend variables are included in browser code, so do not place secrets in `VITE_*` variables.

## Verification

Check the backend health endpoint:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
```

Run backend tests:

```powershell
cd urban-air-quality-assistant/backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run frontend tests and checks:

```powershell
cd urban-air-quality-assistant/frontend
npm test
npm run build
npm exec tsc -- --noEmit -p tsconfig.app.json --incremental false
npm run lint
```

## Data limitations

Open-Meteo readings are modelled outdoor estimates, not measurements from an indoor sensor or local ground station. Indoor air quality is not inferred from outdoor concentrations. Missing readings remain missing rather than being replaced with zero or invented values.
