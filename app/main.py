from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.db.pool import get_pool, close_pool
from app.routes.products import router as products_router
from app.routes.orders import router as orders_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()   # connect on startup (with retries)
    yield
    await close_pool() # clean shutdown


app = FastAPI(
    title="DB Concurrency Control Simulator",
    description="Pessimistic vs Optimistic locking for inventory management",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health():
    pool = await get_pool()
    await pool.fetchval("SELECT 1")
    return {"status": "healthy"}


app.include_router(products_router, prefix="/api/products", tags=["products"])
app.include_router(orders_router,   prefix="/api/orders",   tags=["orders"])
