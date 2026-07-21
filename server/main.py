from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Field, SQLModel, select

# 1. Async SQLite Database Setup
# Using the `sqlite+aiosqlite` protocol for non-blocking async DB operations
sqlite_file = "database.db"
sqlite_url = f"sqlite+aiosqlite:///{sqlite_file}"

connect_args = {"check_same_thread": False}
engine = create_async_engine(sqlite_url, echo=True, connect_args=connect_args)


class SurfSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rating: float = Field(index=True)


async def create_db_and_tables():
    """Asynchronously create tables using the metadata runner."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# 2. Modern FastAPI Lifespan Handler (replaces deprecated @app.on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create DB tables
    await create_db_and_tables()
    yield
    # Shutdown: clean up engine connections
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


# 3. Async Session Dependency
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# --- Route Handlers ---


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.post("/sessions/", status_code=status.HTTP_201_CREATED)
async def create_session(
    surfsession: SurfSession, session_dep: SessionDep
) -> SurfSession:
    try:
        session_dep.add(surfsession)
        await session_dep.commit()
        await session_dep.refresh(surfsession)
        return surfsession
    except SQLAlchemyError as e:
        await session_dep.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating the session.",
        ) from e


@app.get("/sessions/")
async def read_sessions(
    session_dep: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
) -> list[SurfSession]:
    try:
        statement = select(SurfSession).offset(offset).limit(limit)
        # Use .scalars() instead of .exec()
        results = await session_dep.scalars(statement)
        return list(results.all())
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while fetching sessions.",
        ) from e

@app.get("/sessions/{session_id}")
async def read_session(
    session_id: int, session_dep: SessionDep
) -> SurfSession:
    try:
        surfsession = await session_dep.get(SurfSession, session_id)
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while retrieving the session.",
        ) from e

    if not surfsession:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SurfSession with id {session_id} not found",
        )
    return surfsession


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: int, session_dep: SessionDep) -> dict:
    try:
        surfsession = await session_dep.get(SurfSession, session_id)
        if not surfsession:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SurfSession with id {session_id} not found",
            )

        await session_dep.delete(surfsession)
        await session_dep.commit()
        return {"ok": True}
    except HTTPException:
        # Re-raise explicit 404s without triggering generic database error
        raise
    except SQLAlchemyError as e:
        await session_dep.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while deleting the session.",
        ) from e