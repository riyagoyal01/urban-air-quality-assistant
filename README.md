# Urban Air Quality Assistant

A React + FastAPI application that combines modelled outdoor air-quality data with household-specific indoor guidance and a local LLM chat assistant.

> **Important data limitation:** Open-Meteo provides modelled outdoor estimates, not indoor sensor readings or necessarily measurements from a nearby ground station. The application does not infer indoor pollutant concentrations from outdoor data.

## Features

- Search for a city and view current modelled pollutant readings
- Explore hourly PM2.5 data
- Receive precautionary, household-oriented outdoor recommendations
- Get indoor pollution-reduction guidance based on purifier availability and cooking fuel
- Ask follow-up questions using a local Ollama model
- Handle missing pollutant values without silently replacing them with zero

## Architecture

The application source is currently in the `urban-air-quality-assistant/` directory:

- `urban-air-quality-assistant/frontend/`: React 19, TypeScript, and Vite
- `urban-air-quality-assistant/backend/main.py`: FastAPI endpoints and recommendation logic
- `urban-air-quality-assistant/backend/tests/`: backend tests
- `urban-air-quality-assistant/frontend/tests/`: frontend utility and regression tests
- Open-Meteo: geocoding and modelled air-quality data
- Ollama (`qwen3:4b` by default): local chat inference

## Requirements

- Python 3.12+
- Node.js 22.12+ (or a compatible supported release)
- npm
- [Ollama](https://ollama.com/) installed and running
- Internet access for Open-Meteo requests

## Run locally (Windows PowerShell)

### 1. Backend

```powershell
cd urban-air-quality-assistant/backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

The API runs at `http://127.0.0.1:8000` by default.

### 2. Ollama

In a separate terminal:

```powershell
ollama pull qwen3:4b
ollama serve
```

Keep Ollama running while using chat. The chat feature depends on the local Ollama service; the dashboard's Open-Meteo features do not require Ollama.

### 3. Frontend

In another terminal:

```powershell
cd urban-air-quality-assistant/frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`).

## Configuration

Backend settings are in `urban-air-quality-assistant/backend/.env.example`:

| Variable | Purpose |
| --- | --- |
| `BACKEND_HOST` / `BACKEND_PORT` | FastAPI bind address |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `OLLAMA_HOST` / `OLLAMA_MODEL` | Local Ollama endpoint and model |
| `OLLAMA_TIMEOUT_SECONDS` | Chat request timeout |
| `AIR_QUALITY_URL` / `AIR_QUALITY_TIMEOUT_SECONDS` | Open-Meteo air-quality endpoint and timeout |
| `LOCATION_URL` / `LOCATION_TIMEOUT_SECONDS` | Open-Meteo geocoding endpoint and timeout |

Frontend configuration is in `urban-air-quality-assistant/frontend/.env.example`:

- `VITE_API_BASE_URL`: FastAPI base URL

Do not put secrets in `VITE_*` variables; Vite exposes them to browser code. Local `.env` files are ignored by Git.

## Tests and checks

Backend:

```powershell
cd urban-air-quality-assistant/backend
python -m unittest discover -s tests -v
```

Frontend:

```powershell
cd urban-air-quality-assistant/frontend
npm ci
npm test
npm run build
npm run lint
```

Backend health check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
```

## Limitations

- Air-quality values are modelled outdoor estimates and have spatial uncertainty.
- No indoor sensor data is collected; indoor air quality cannot be measured by this application.
- Recommendations are precautionary application logic, not official AQI classifications, medical advice, or a substitute for local public-health guidance.
- Chat requires the configured Ollama model to be available locally.
- A public deployment would need a separately hosted backend and an Ollama inference service reachable by that backend; the local-development configuration is not a production deployment recipe.

## License

MIT. See [LICENSE](LICENSE).
