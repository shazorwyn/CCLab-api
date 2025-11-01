from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class DeviceSignal(BaseModel):
    id: str
    lat: float
    lng: float


class TargetLocation(BaseModel):
    name: str
    lat: float
    lng: float


class TargetResponse(BaseModel):
    status: str
    response: list[TargetLocation]


@app.get("/")
async def root():
    return {"message": "Welcome to the [] app!"}


@app.post("/api/v1/fuel-alert", response_model=TargetResponse)
async def fuel_alert(signal: DeviceSignal):
    print(
        f"Received signal from {signal.id} at ({signal.lat}, {signal.lng})")

    mock_pumps = [
        TargetLocation(
            name="Mock Pump 1 (Nearest)",
            lat=signal.lat + 0.005,
            lng=signal.lng - 0.002,
        ),
        TargetLocation(
            name="Mock Pump 2",
            lat=signal.lat - 0.01,
            lng=signal.lng + 0.007,
        )
    ]

    return TargetResponse(
        status="success",
        response=mock_pumps
    )
