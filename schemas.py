from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=72, min_length=8)


class UserResponse(BaseModel):
    id: int
    email: EmailStr

    class Config:
        from_attributes = True


class DeviceResponse(BaseModel):
    device_id: str
    api_key: str

    class Config:
        from_attributes = True


class RegisterResponse(BaseModel):
    user: UserResponse
    device: DeviceResponse

    class Config:
        from_attributes = True
