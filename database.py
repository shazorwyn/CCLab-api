from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator
from fastapi import Depends

ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./user_data.db"

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False
)

Base = declarative_base()

AsyncSessionLocal = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

AsyncSessionDependency = Depends(get_async_session)


async def create_db_and_tables():
    """Create all database tables defined in the Base metadata."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
