# Standard library
import os
import secrets
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

# Third-party
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import delete, text, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from database import (
    create_db_and_tables,
    AsyncSessionLocal,
    AsyncSessionDependency,
)
from models import FuelStationCache, User, Device, SignalLog
from schemas import RegisterResponse, UserCreate
from security import Hasher
from auth import create_access_token, get_current_user

load_dotenv()
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")


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


# 🧹 Cleanup old signal logs (older than 24 hours)


async def cleanup_old_signals_loop():
    while True:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "DELETE FROM signal_logs WHERE received_at < datetime('now', '-1 day')")
            )
            await db.commit()
            print("[CLEANUP] Removed old signal logs (older than 24h)")
        await asyncio.sleep(6 * 60 * 60)  # run every 6 hours

# 🧹 Cleanup old fuel station cache (older than 24 hours)


async def cleanup_old_cache_loop():
    while True:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "DELETE FROM fuel_station_cache WHERE cached_at < datetime('now', '-1 day')")
            )
            await db.commit()
            print("[CLEANUP] Removed old cached fuel stations (older than 24h)")
        await asyncio.sleep(6 * 60 * 60)  # run every 6 hours


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()

    asyncio.create_task(cleanup_old_signals_loop())
    asyncio.create_task(cleanup_old_cache_loop())

    print("[SYSTEM] Startup complete — 24h cleanup schedulers running")
    yield
    print("[SYSTEM] Backend shutting down gracefully 💤")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


async def get_device_from_api_key(
    x_api_key: str = Header(None),
    db: AsyncSession = AsyncSessionDependency
):
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    result = await db.execute(select(Device).where(Device.api_key == x_api_key))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return device


@app.get("/")
async def root():
    return {"message": "Welcome to the [] app!"}


@auth_router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = AsyncSessionDependency):

    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = Hasher.get_password_hash(user_in.password)
    new_user = User(email=user_in.email, hashed_password=hashed_password)
    db.add(new_user)
    await db.flush()  # ensure new_user.id is available before commit

    device = Device(
        device_id=f"DEV_{new_user.id:04d}",
        api_key=secrets.token_hex(16),
        user_id=new_user.id,
    )
    db.add(device)

    await db.commit()
    await db.refresh(new_user)
    await db.refresh(device)

    return {
        "user": {"id": new_user.id, "email": new_user.email},
        "device": {
            "device_id": device.device_id,
            "api_key": device.api_key
        }
    }


@auth_router.post("/login")
async def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = AsyncSessionDependency
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not Hasher.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email}

app.include_router(auth_router)


@app.post("/api/v1/fuel-alert")
async def fuel_alert(
    signal: DeviceSignal,
    device: Device = Depends(get_device_from_api_key),
    db: AsyncSession = AsyncSessionDependency,
):
    print(
        f"[DEVICE] {device.device_id} sent signal at ({signal.lat}, {signal.lon})")

    # save signal log
    log = SignalLog(
        device_id=device.device_id,
        lat=signal.lat,
        lon=signal.lon,
        soc=signal.soc,
        time=signal.time,
    )
    db.add(log)
    await db.commit()

    places_url = "https://api.geoapify.com/v2/places"
    params = {
        "categories": "service.vehicle.fuel",
        "bias": f"proximity:{signal.lon},{signal.lat}",
        "limit": 5,
        "apiKey": GEOAPIFY_API_KEY,
    }

    response = requests.get(places_url, params=params)
    response.raise_for_status()
    data = response.json()

    target_results = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        if "coordinates" in geom and props.get("name"):
            lon, lat = geom["coordinates"]
            target_results.append({
                "name": props["name"],
                "lat": lat,
                "lon": lon,
                "vicinity": props.get("formatted", "Address N/A"),
            })

    await db.execute(
        delete(FuelStationCache).where(
            FuelStationCache.device_id == device.device_id)
    )  # clear old cache

    for s in target_results:
        db.add(FuelStationCache(
            device_id=device.device_id,
            name=s["name"],
            lat=s["lat"],
            lon=s["lon"],
            vicinity=s["vicinity"]
        ))
    await db.commit()

    # print(
    #     f"[FUEL ALERT] Device {device.device_id} - SOC: {signal.soc}%\n"
    #     f"[Status] {'Critical' if signal.soc < 20 else 'Non-critical'}\n"
    #     f"[Location] {signal.lat}, {signal.lon}\n"
    #     f"[Nearby Fuel Stations] {target_results}"
    # )

    return {"status": "success", "response": target_results}


@app.get("/api/v1/device/stations")
async def get_latest_stations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = AsyncSessionDependency
):
    result = await db.execute(select(Device).where(Device.user_id == current_user.id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=404, detail="No device linked to this user")

    station_result = await db.execute(
        select(FuelStationCache).where(
            FuelStationCache.device_id == device.device_id)
    )
    stations = station_result.scalars().all()

    if not stations:
        raise HTTPException(status_code=404, detail="No cached stations found")

    response = [
        {"name": s.name, "lat": s.lat, "lon": s.lon, "vicinity": s.vicinity}
        for s in stations
    ]

    return {"status": "success", "response": response}


@app.get("/api/v1/device/me")
async def get_my_device(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = AsyncSessionDependency
):
    result = await db.execute(select(Device).where(Device.user_id == current_user.id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=404, detail="No device linked to this user")

    return {
        "device_id": device.device_id,
        "name": device.name,
        "model": device.model
    }


@app.get("/api/v1/device/latest")
async def get_latest_signal(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = AsyncSessionDependency
):
    result = await db.execute(select(Device).where(Device.user_id == current_user.id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=404, detail="No device linked to this user")

    log_result = await db.execute(
        select(SignalLog)
        .where(SignalLog.device_id == device.device_id)
        .order_by(SignalLog.time.desc())
        .limit(1)
    )
    latest_log = log_result.scalar_one_or_none()

    if not latest_log:
        raise HTTPException(status_code=404, detail="No signals received yet")

    return {
        "device_id": device.device_id,
        "lat": latest_log.lat,
        "lon": latest_log.lon,
        "soc": latest_log.soc,
        "time": latest_log.time
    }
