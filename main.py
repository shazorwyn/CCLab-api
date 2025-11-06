from fastapi import FastAPI, HTTPException, APIRouter, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
from datetime import datetime
from dotenv import load_dotenv
import os
import requests

from database import create_db_and_tables, AsyncSessionDependency
from schemas import UserCreate, UserResponse
from models import User
from security import Hasher
from auth import create_access_token, get_current_user  # <-- NEW

load_dotenv()
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # your Vite frontend
        "http://172.20.84.183:5173"  # optional if accessing frontend via IP
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = AsyncSessionDependency
):
    query = select(User).where(User.email == user_in.email)
    result = await db.execute(query)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = Hasher.get_password_hash(user_in.password)

    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


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


app.include_router(auth_router)


@app.get("/")
async def root():
    return {"message": "Welcome to the [] app!"}


@app.post("/api/v1/fuel-alert", response_model=TargetResponse)
async def fuel_alert(
    signal: DeviceSignal,
    current_user: User = Depends(get_current_user)  # <-- protection
):
    print(
        f"Received signal at ({signal.lat}, {signal.lon})")
    if not GEOAPIFY_API_KEY:
        raise HTTPException(
            status_code=500, detail="Geoapify api key is not configured."
        )

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

    target_results: list[TargetLocation] = []
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
    print(target_results)
    return TargetResponse(status="success", response=target_results)
