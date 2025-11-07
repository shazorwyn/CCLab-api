from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Link to device
    device = relationship("Device", back_populates="owner", uselist=False)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="device")

    # optional meta fields
    name = Column(String, default="My Device")
    model = Column(String, nullable=True)


class SignalLog(Base):
    __tablename__ = "signal_logs"

    id = Column(Integer, primary_key=True)
    device_id = Column(String, index=True)
    lat = Column(Float)
    lon = Column(Float)
    soc = Column(Float)
    time = Column(DateTime)
    received_at = Column(DateTime, default=datetime.now(timezone.utc))


class FuelStationCache(Base):
    __tablename__ = "fuel_station_cache"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("devices.device_id"))
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    vicinity = Column(String)

    # Relationship (optional)
    device = relationship("Device", backref="cached_stations")
    cached_at = Column(DateTime, default=datetime.now(
        timezone.utc), nullable=False)

    def __repr__(self):
        return f"<FuelStationCache(device={self.device_id}, name={self.name})>"
