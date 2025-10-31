from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class DeviceSignal(BaseModel):
    id: str
    latitude: float
    longitude: float


class TargetLocation(BaseModel):
    name: str
    latitude: float
    longitude: float


class TargetResponse(BaseModel):
    status: str
    response: list[TargetLocation]


@app.get("/")
async def root():
    return {"message": "Welcome to the [] app!"}
