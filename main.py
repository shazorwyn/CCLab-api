from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from datetime import datetime
from dotenv import load_dotenv
import os
import requests

load_dotenv()
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")


app = FastAPI()


class DeviceSignal(BaseModel):
    lat: float = Field(...)
    lon: float = Field(...)
    soc: float = Field(..., ge=0, le=100)
    time: datetime = Field(...)


class TargetLocation(BaseModel):
    name: str
    lat: float
    lon: float
    vicinity: str


class TargetResponse(BaseModel):
    status: str
    response: list[TargetLocation]


@app.get("/")
async def root():
    return {"message": "Welcome to the [] app!"}


@app.post("/api/v1/fuel-alert", response_model=TargetResponse)
async def fuel_alert(signal: DeviceSignal):
    print(f"Received signal at ({signal.lat}, {signal.lon})")
    if not GEOAPIFY_API_KEY:
        raise HTTPException(
            status_code=500, detail="Geoapify api key is not configured.")
    places_url = "https://api.geoapify.com/v2/places"

    params = {
        "categories": "service.vehicle.fuel",
        "bias": f"proximity:{signal.lon},{signal.lat}",
        "limit": 5,
        "apiKey": GEOAPIFY_API_KEY
    }
    try:
        response = requests.get(places_url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"Geoapify API Request failed: {e}")
        raise HTTPException(
            status_code=503, detail="External mapping service is currently unavailable."
        )

    target_results: TargetLocation = []
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        if 'coordinates' in geometry and properties.get("name"):
            lon, lat = geometry["coordinates"]

            target_results.append(
                TargetLocation(
                    name=properties["name"],
                    lat=lat,
                    lon=lon,
                    vicinity=properties.get("formatted", "Address N/A")
                )
            )

    return TargetResponse(
        status="success",
        response=target_results
    )
