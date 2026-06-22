from fastapi import FastAPI

from src.routes.catalog import router as catalog_router
from src.routes.cart import router as cart_router
from src.routes.orders import router as orders_router

app = FastAPI(title="NeoMarket B2C Service", version="1.0.0")

app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)


@app.get("/healthz", tags=["Health"])
def healthcheck() -> dict:
    return {"status": "ok"}
