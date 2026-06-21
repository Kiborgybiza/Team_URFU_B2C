from fastapi import FastAPI

app = FastAPI(title="NeoMarket B2C Service", version="1.0.0")


@app.get("/healthz", tags=["Health"])
def healthcheck() -> dict:
    return {"status": "ok"}
