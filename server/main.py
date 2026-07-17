from fastapi import FastAPI # type: ignore[import]

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}