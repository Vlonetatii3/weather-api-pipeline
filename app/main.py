from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}
