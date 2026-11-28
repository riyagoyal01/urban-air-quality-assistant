from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal
import httpx
import json
import ollama
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="Urban Air Quality Assistant")

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

AIR_QUALITY_URL = os.getenv(
    "AIR_QUALITY_URL",
    "https://air-quality-api.open-meteo.com/v1/air-quality",
)
LOCATION_URL = os.getenv(
    "LOCATION_URL",
    "https://geocoding-api.open-meteo.com/v1/search",
)


def positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if 1 <= value <= 65535 else default
    except (TypeError, ValueError):
        return default


OLLAMA_HOST = os.getenv("OLLAMA_HOST")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_SECONDS = positive_float_env("OLLAMA_TIMEOUT_SECONDS", 60)
AIR_QUALITY_TIMEOUT_SECONDS = positive_float_env("AIR_QUALITY_TIMEOUT_SECONDS", 20)
LOCATION_TIMEOUT_SECONDS = positive_float_env("LOCATION_TIMEOUT_SECONDS", 15)
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = positive_int_env("BACKEND_PORT", 8000)

POLLUTANTS = [
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "carbon_monoxide",
]

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "message": "Urban Air Quality Assistant backend is running"
    }

@app.get("/api/air-quality")
async def get_air_quality(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(POLLUTANTS),
        "hourly": ",".join(POLLUTANTS),
        "forecast_days": 2,
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=AIR_QUALITY_TIMEOUT_SECONDS) as client:
            response = await client.get(AIR_QUALITY_URL, params=params)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Open-Meteo returned invalid JSON")
        if "latitude" not in data or "longitude" not in data:
            raise KeyError("Missing location coordinates")

        raw_current = data.get("current")
        current = raw_current if isinstance(raw_current, dict) else {}
        raw_current_units = data.get("current_units")
        current_units = raw_current_units if isinstance(raw_current_units, dict) else {}
        raw_hourly = data.get("hourly")
        hourly = raw_hourly if isinstance(raw_hourly, dict) else {}
        raw_hourly_units = data.get("hourly_units")
        hourly_units = raw_hourly_units if isinstance(raw_hourly_units, dict) else {}

        normalized_current = {
            pollutant: current.get(pollutant)
            if isinstance(current.get(pollutant), (int, float)) and not isinstance(current.get(pollutant), bool)
            else None
            for pollutant in POLLUTANTS
        }
        normalized_hourly = {
            key: [
                value
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
                for value in hourly.get(key, [])
            ]
            if isinstance(hourly.get(key), list)
            else []
            for key in POLLUTANTS
        }
        normalized_hourly["time"] = (
            hourly.get("time")
            if isinstance(hourly.get("time"), list)
            and all(isinstance(value, str) for value in hourly.get("time"))
            else []
        )

        return {
            "location": {
                "latitude": data["latitude"],
                "longitude": data["longitude"],
                "timezone": data.get("timezone"),
            },
            "current": normalized_current,
            "current_units": {
                key: value
                for key, value in current_units.items()
                if isinstance(value, str)
            },
            "hourly": normalized_hourly,
            "hourly_units": {
                key: value
                for key, value in hourly_units.items()
                if isinstance(value, str)
            },
            "source": "Open-Meteo Air Quality API",
            "model_note": (
                "Global CAMS data has approximately 45 km spatial "
                "resolution. Values are model estimates, not local "
                "ground-station measurements."
            ),
        }

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="The air-quality service timed out. Please try again."
        )
    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="The air-quality service returned an external API error."
        )
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Could not retrieve air-quality data. Please try again."
        )

@app.get("/api/search-location")
async def search_location(name: str = Query(min_length=2, max_length=100)):
    try:
        async with httpx.AsyncClient(timeout=LOCATION_TIMEOUT_SECONDS) as client:
            response = await client.get(
                LOCATION_URL,
                params={
                    "name": name,
                    "count": 5,
                    "language": "en",
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, dict):
            raise ValueError("Location service returned invalid JSON")
        raw_results = data.get("results")
        if raw_results is None:
            raw_results = []
        if not isinstance(raw_results, list):
            raise ValueError("Location service returned invalid results")

        return {
            "results": [
                {
                    "name": place["name"],
                    "admin1": place.get("admin1"),
                    "country": place.get("country"),
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                }
                for place in raw_results
                if isinstance(place, dict)
                and isinstance(place.get("name"), str)
                and isinstance(place.get("latitude"), (int, float))
                and isinstance(place.get("longitude"), (int, float))
            ]
        }

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Location search timed out. Please try again."
        )
    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="The location service returned an external API error."
        )
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Location search is temporarily unavailable."
        )
    
class RecommendationRequest(BaseModel):
    pm2_5: float | None = None
    pm10: float | None = None
    ozone: float | None = None
    nitrogen_dioxide: float | None = None
    pm2_5_unit: str | None = None
    pm10_unit: str | None = None
    ozone_unit: str | None = None
    nitrogen_dioxide_unit: str | None = None
    household: str = "family_with_children"


@app.post("/api/recommendations")
def get_recommendations(request: RecommendationRequest):
    recommendations = []
    pm2_5_unit = request.pm2_5_unit or "unit not supplied"
    pm10_unit = request.pm10_unit or "unit not supplied"

    if request.pm2_5 is not None and request.pm2_5 >= 35:
        recommendations.append({
            "category": "Outdoor activities",
            "priority": "High",
            "action": "Move children's outdoor play and exercise indoors for now.",
            "reason": (
                f"PM2.5 is {request.pm2_5} {pm2_5_unit}. "
                "Fine particles can penetrate deep into the lungs."
            ),
            "alternative": "Indoor games, reading or light indoor activities."
        })
    elif request.pm2_5 is not None and request.pm2_5 >= 15:
        recommendations.append({
            "category": "Outdoor activities",
            "priority": "Not assessed",
            "action": "Check the pollution forecast before planning outdoor play.",
            "reason": (
                f"PM2.5 is {request.pm2_5} {pm2_5_unit}. "
                "Reducing unnecessary exposure is a sensible precaution."
            ),
            "alternative": "Choose shorter outdoor activities when conditions are comparatively better."
        })
    elif request.pm2_5 is None:
        recommendations.append({
            "category": "Outdoor activities",
            "priority": "Moderate",
            "action": "Check local outdoor conditions before planning children's outdoor play.",
            "reason": "The modelled outdoor PM2.5 reading is missing, so no PM2.5 threshold-based activity advice is available.",
            "alternative": "Use local official guidance or a later reading before deciding."
        })
    else:
        recommendations.append({
            "category": "Outdoor activities",
            "priority": "Low",
            "action": "Check the forecast and local conditions before outdoor play.",
            "reason": "Current modelled PM2.5 is relatively lower than our advisory thresholds.",
            "alternative": "Continue normal activities while monitoring changing conditions."
        })

    if request.pm10 is not None and request.pm10 >= 50:
        recommendations.append({
            "category": "Indoor air",
            "priority": "Moderate",
            "action": "Reduce indoor dust and avoid sweeping or dusting that raises particles.",
            "reason": f"Modelled PM10 concentration is {request.pm10} {pm10_unit}.",
            "alternative": "Use a damp cloth for cleaning and keep dusty areas undisturbed."
        })

    recommendations.append({
        "category": "Household protection",
        "priority": "Moderate",
        "action": "Avoid incense, mosquito coils, smoking and unnecessary combustion indoors.",
        "reason": "These activities can introduce additional pollutants into indoor air.",
        "alternative": "Use non-combustion alternatives where practical."
    })

    recommendations.append({
        "category": "School commute",
        "priority": "Moderate",
        "action": "Prefer less congested roads and avoid waiting beside idling vehicles.",
        "reason": "Vehicle exhaust can increase exposure to traffic-related pollution.",
        "alternative": "Choose a quieter route or a less congested pickup point."
    })

    return {
        "household": request.household,
        "recommendations": recommendations,
        "disclaimer": (
            "These are precautionary recommendations based on modelled "
            "pollutant concentrations, not an official AQI or medical advice. "
            "The thresholds are internal advisory triggers, not health standards."
        )
    }

class IndoorRequest(BaseModel):
    pm2_5: float | None = None
    pm2_5_unit: str | None = None
    has_air_purifier: bool = False
    cooking_fuel: str = "lpg"


@app.post("/api/indoor-advice")
def indoor_advice(request: IndoorRequest):
    advice = []

    if request.pm2_5 is not None and request.pm2_5 >= 35:
        advice.append({
            "title": "Keep outdoor pollution outside",
            "action": "Keep windows and doors closed during periods of elevated outdoor pollution.",
            "reason": "Outdoor fine particles can enter indoor spaces."
        })
    elif request.pm2_5 is None:
        advice.append({
            "title": "Use available readings before changing ventilation",
            "action": "Check outdoor conditions and use an indoor monitor before making ventilation decisions.",
            "reason": "The modelled outdoor PM2.5 reading is missing; indoor air was not measured."
        })
    else:
        advice.append({
            "title": "Ventilate thoughtfully",
            "action": "Ventilate when outdoor air is comparatively cleaner.",
            "reason": "Fresh-air exchange helps remove indoor pollutants, but outdoor conditions matter."
        })

    advice.append({
        "title": "Reduce indoor dust",
        "action": "Use a damp cloth or mop instead of dry dusting or sweeping.",
        "reason": "Dry cleaning can resuspend particles that people may breathe."
    })

    if request.cooking_fuel in {"wood", "coal"}:
        cooking_action = (
            "If practical, switch to electricity or LPG. While cooking, use "
            "a kitchen exhaust fan that vents outdoors, if available."
        )
        cooking_reason = (
            f"Burning {request.cooking_fuel} can generate substantial smoke "
            "and fine particles indoors."
        )
    elif request.cooking_fuel == "electricity":
        cooking_action = (
            "Use a kitchen exhaust fan that vents outdoors while cooking, "
            "and avoid overheating food or oil."
        )
        cooking_reason = (
            "Electric cooking avoids fuel-combustion emissions, but cooking "
            "can still generate particles."
        )
    elif request.cooking_fuel == "lpg":
        cooking_action = (
            "Use a kitchen exhaust fan that vents outdoors while cooking, "
            "if available."
        )
        cooking_reason = (
            "LPG burns more cleanly than solid fuels, but can still produce "
            "nitrogen dioxide and cooking particles."
        )
    else:
        cooking_action = (
            "Use a kitchen exhaust fan that vents outdoors while cooking, "
            "if available, and avoid using smoky fuels indoors."
        )
        cooking_reason = (
            "Some cooking fuels and cooking processes can generate smoke "
            "and other indoor pollutants."
        )

    advice.append({
        "title": "Reduce cooking pollution",
        "action": cooking_action,
        "reason": cooking_reason
    })

    advice.append({
        "title": "Avoid indoor smoke",
        "action": "Avoid incense, mosquito coils, smoking and unnecessary burning indoors.",
        "reason": "Combustion produces additional indoor air pollution."
    })

    if request.has_air_purifier:
        advice.append({
            "title": "Use your air purifier effectively",
            "action": "Use a correctly sized HEPA air purifier in the room where children spend the most time.",
            "reason": "HEPA filtration can reduce airborne particles when properly sized and maintained."
        })
    else:
        advice.append({
            "title": "Consider particle filtration",
            "action": "If affordable, consider a correctly sized HEPA air purifier for frequently occupied rooms.",
            "reason": "Mechanical particle filtration can reduce indoor airborne particles."
        })

    return {
        "household": "family_with_children",
        "indoor_advice": advice,
        "important_note": (
            "These are general indoor pollution reduction measures. "
            "Outdoor modelled PM2.5 does not measure indoor air quality. "
            "An indoor monitor is needed to assess indoor pollutant levels."
        )
    }


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    pm2_5: float | None = None
    pm10: float | None = None
    ozone: float | None = None
    nitrogen_dioxide: float | None = None
    pm2_5_unit: str | None = Field(default=None, max_length=100)
    pm10_unit: str | None = Field(default=None, max_length=100)
    ozone_unit: str | None = Field(default=None, max_length=100)
    nitrogen_dioxide_unit: str | None = Field(default=None, max_length=100)
    household: str = Field(max_length=100)
    has_air_purifier: bool
    cooking_fuel: str = Field(max_length=100)
    recommendations: list[dict] | None = Field(default=None, max_length=100)
    history: list[ChatHistoryItem] = Field(default_factory=list, max_length=20)


def format_authoritative_recommendations(recommendations: list[dict] | None) -> str | None:
    if not recommendations:
        return None

    formatted = []
    for recommendation in recommendations:
        action = recommendation.get("action")
        priority = recommendation.get("priority")
        if not isinstance(action, str) or not action.strip():
            return (
                "A supplied dashboard recommendation is incomplete because it "
                "does not include an actionable direction. I cannot safely guess "
                "or add one."
            )
        if not isinstance(priority, str) or not priority.strip():
            return (
                f"- {action.strip()}\n"
                "  Priority is not supplied for this dashboard recommendation."
            )
        formatted.append(
            f"- **{priority.strip()} priority**: {action.strip()}"
        )
    return "\n".join(formatted)


def action_plan_question(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in (
        "what should",
        "what can",
        "what do",
        "action plan",
        "do today",
        "play outside",
        "outdoor activity",
        "outdoor activities",
    ))


def window_advice_question(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in (
        "window",
        "windows",
        "open ventilation",
        "open the door",
        "open doors",
    ))


def call_ollama(messages: list[dict]) -> object:
    client = ollama.Client(
        host=OLLAMA_HOST,
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    try:
        return client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
        )
    finally:
        client.close()


def validated_chat_history(history: list[ChatHistoryItem]) -> list[dict]:
    validated = []
    for item in history[-20:]:
        content = item.content.strip()
        if item.role not in ("user", "assistant") or not content:
            continue
        validated.append({"role": item.role, "content": content})
    return validated


def extract_ollama_answer(response: object) -> str | None:
    if isinstance(response, dict):
        message = response.get("message")
        if not isinstance(message, dict):
            return None
        answer = message.get("content")
    else:
        message = getattr(response, "message", None)
        answer = getattr(message, "content", None)

    if not isinstance(answer, str):
        return None
    answer = answer.strip()
    if not answer:
        return None
    if len(answer) > 20_000:
        return None
    return answer


@app.post("/api/chat")
def chat(request: ChatRequest):
    recommendations_input = request.recommendations

    if window_advice_question(request.question):
        matching = []
        if recommendations_input:
            for recommendation in recommendations_input:
                searchable = " ".join(
                    str(recommendation.get(field, ""))
                    for field in ("action", "reason", "alternative", "category")
                ).lower()
                if any(term in searchable for term in (
                    "window", "windows", "ventilat", "door", "doors"
                )):
                    matching.append(recommendation)

        if matching:
            formatted = format_authoritative_recommendations(matching)
            if formatted:
                return {
                    "answer": (
                        "The dashboard's authoritative window guidance is:\n"
                        f"{formatted}"
                    )
                }
        return {
            "answer": (
                "The dashboard has not supplied a window-specific recommendation "
                "for these conditions. I cannot invent advice to open or close "
                "windows."
            )
        }

    if action_plan_question(request.question):
        formatted = format_authoritative_recommendations(recommendations_input)
        if formatted:
            return {
                "answer": (
                    "The dashboard's authoritative actions are:\n"
                    f"{formatted}"
                )
            }
        return {
            "answer": (
                "No dashboard recommendations are available, so I cannot provide "
                "an authoritative action plan or invent actions."
            )
        }

    system_prompt = (
        "Answer concisely and factually using supplied dashboard readings and "
        "actual household preferences. For simple factual questions, answer "
        "in 1-3 sentences; for action plans, use a short prioritized bullet "
        "list. Do not repeat disclaimers or list readings unless relevant. "
        "The supplied outdoor values are modelled outdoor readings, not "
        "indoor measurements. Never infer or estimate indoor pollutant "
        "concentrations from outdoor readings, and do not claim indoor air is "
        "clean or polluted without indoor measurements. Use the existing "
        "backend recommendations as the authoritative action plan: do not "
        "invent actions, alter them, or add, rename, or reinterpret their "
        "priority labels. If recommendations are not provided, do not invent "
        "a recommendation list. Never invent AQI categories, health "
        "classifications, thresholds, or priorities from pollutant "
        "concentrations. Do not recommend opening windows while outdoor "
        "pollution is elevated unless a supplied recommendation explicitly "
        "supports it for the current conditions. Cooking can generate "
        "particles with any fuel, including electricity. When a question "
        "poses a hypothetical scenario, answer that scenario first; keep it "
        "separate from the actual household preferences and mention actual "
        "preferences only when relevant. If a needed value is marked not "
        "provided, say so without guessing."
    )
    readings = (
        "PM2.5: "
        f"{request.pm2_5 if request.pm2_5 is not None else 'not provided'}"
        f"{' ' + request.pm2_5_unit if request.pm2_5 is not None and request.pm2_5_unit else ''}\n"
        "PM10: "
        f"{request.pm10 if request.pm10 is not None else 'not provided'}"
        f"{' ' + request.pm10_unit if request.pm10 is not None and request.pm10_unit else ''}\n"
        "Ozone: "
        f"{request.ozone if request.ozone is not None else 'not provided'}"
        f"{' ' + request.ozone_unit if request.ozone is not None and request.ozone_unit else ''}\n"
        "Nitrogen dioxide: "
        f"{request.nitrogen_dioxide if request.nitrogen_dioxide is not None else 'not provided'}"
        f"{' ' + request.nitrogen_dioxide_unit if request.nitrogen_dioxide is not None and request.nitrogen_dioxide_unit else ''}"
    )
    recommendations = (
        json.dumps(request.recommendations, ensure_ascii=False)
        if request.recommendations is not None
        else "not provided"
    )

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "ACTUAL DASHBOARD CONTEXT\n"
                        "Outdoor readings below are modelled; they are not "
                        "indoor measurements.\n"
                        f"{readings}\n"
                        "Indoor pollutant measurements: not provided.\n"
                        "Actual household preferences:\n"
                        f"Household type: {request.household}\n"
                        "Air purifier available: "
                        f"{'Yes' if request.has_air_purifier else 'No'}\n"
                        f"Cooking fuel: {request.cooking_fuel}\n"
                        "Existing backend recommendations and priorities "
                        "(authoritative; preserve as supplied): "
                        f"{recommendations}\n"
                        "Treat any hypothetical preferences in the question "
                        "as a scenario, not as the actual household profile."
                ),
            },
        ]
        messages.extend(validated_chat_history(request.history))
        current_question = request.question.strip()
        if not current_question:
            raise HTTPException(
                status_code=422,
                detail="The question must not be empty.",
            )
        messages.append({"role": "user", "content": current_question})
        response = call_ollama(messages)
    except (ollama.RequestError, ollama.ResponseError, httpx.HTTPStatusError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The local air-quality assistant is temporarily unavailable.",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="The local air-quality assistant timed out. Please try again.",
        ) from exc
    except (httpx.HTTPError, ConnectionError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The local air-quality assistant is temporarily unavailable.",
        ) from exc

    answer = extract_ollama_answer(response)
    if answer is None:
        raise HTTPException(
            status_code=502,
            detail="The local air-quality assistant returned an invalid response.",
        )

    return {"answer": answer.strip()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
