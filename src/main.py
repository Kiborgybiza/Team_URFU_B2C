from fastapi import FastAPI

from src.routes.catalog import router as catalog_router

app = FastAPI(title="NeoMarket B2C Service", version="1.0.0")

app.include_router(catalog_router)


@app.get("/healthz", tags=["Health"])
def healthcheck() -> dict:
    return {"status": "ok"}
