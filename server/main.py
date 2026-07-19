from typing_extensions import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query # type: ignore[import]
from pydantic import BaseModel
from sqlmodel import Field, SQLModel, create_engine

sqlite_file="database.db"
sqlite_url=f"sqlite:///{sqlite_file}"

connect_args={"check_same_thread": False} # needed for SQLite
engine=create_engine(sqlite_url, echo=True, connect_args=connect_args)

# SQLModel,table=True table in the SQL
class SurfSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True) # id is PK and id=None means its generated
    rating: float = Field(index=True)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with SurfSession(engine) as session:
        yield session

SessionDep = Annotated[SurfSession, Depends(get_session)]

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.on_event("startup")
def on_startup():
    create_db_and_tables()

@app.post("/sessions/")
def create_session(surfsession: SurfSession, session_dep: SessionDep) -> SurfSession:
    session_dep.add(surfsession)
    session_dep.commit()
    session_dep.refresh(surfsession)
    return surfsession

@app.get("/sessions/")
def read_sessions(
    session_dep: SessionDep, 
    offset: int = 0, 
    limit: Annotated[int, Query(le=100)] = 100
) -> list[SurfSession]:
    surfsessions = session_dep.query(SurfSession).offset(offset).limit(limit).all()
    return surfsessions

@app.get("/sessions/{session_id}")
def read_session(session_id: int, session_dep: SessionDep) -> SurfSession:
    surfsession = session_dep.get(SurfSession, session_id)
    if not surfsession:
        raise HTTPException(status_code=404, detail="SurfSession not found")
    return surfsession

@app.delete("/sessions/{session_id}")
def delete_session(session_id: int, session_dep: SessionDep) -> dict:
    surfsession = session_dep.get(SurfSession, session_id)
    if not surfsession:
        raise HTTPException(status_code=404, detail="SurfSession not found")
    session_dep.delete(surfsession)
    session_dep.commit()
    return {"ok": True}