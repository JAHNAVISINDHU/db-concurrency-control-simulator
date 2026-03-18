import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db.pool import get_pool

router = APIRouter()

MAX_RETRIES = 3


class OrderRequest(BaseModel):
    productId: int
    quantity: int = Field(gt=0)
    userId: str


# ---------------------------------------------------------------------------
# POST /api/orders/pessimistic
# Uses SELECT FOR UPDATE — row is locked until transaction commits/rolls back
# ---------------------------------------------------------------------------
@router.post("/pessimistic", status_code=201)
async def pessimistic_order(order: OrderRequest):
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            product = await conn.fetchrow(
                "SELECT id, name, stock, version FROM products WHERE id = $1 FOR UPDATE",
                order.productId
            )

            if not product:
                raise HTTPException(status_code=404, detail="Product not found")

            if product["stock"] < order.quantity:
                await conn.execute(
                    "INSERT INTO orders (product_id, quantity_ordered, user_id, status) "
                    "VALUES ($1, $2, $3, 'FAILED_OUT_OF_STOCK')",
                    order.productId, order.quantity, order.userId
                )
                raise HTTPException(status_code=400, detail="Insufficient stock")

            new_stock = product["stock"] - order.quantity
            await conn.execute(
                "UPDATE products SET stock = $1 WHERE id = $2",
                new_stock, order.productId
            )
            order_id = await conn.fetchval(
                "INSERT INTO orders (product_id, quantity_ordered, user_id, status) "
                "VALUES ($1, $2, $3, 'SUCCESS') RETURNING id",
                order.productId, order.quantity, order.userId
            )

    return {
        "orderId": order_id,
        "productId": order.productId,
        "quantityOrdered": order.quantity,
        "stockRemaining": new_stock,
    }


# ---------------------------------------------------------------------------
# POST /api/orders/optimistic
# Reads without lock, uses version field to detect conflicts — retries up to 3x
# ---------------------------------------------------------------------------
@router.post("/optimistic", status_code=201)
async def optimistic_order(order: OrderRequest):
    pool = await get_pool()

    for attempt in range(1, MAX_RETRIES + 1):
        async with pool.acquire() as conn:
            async with conn.transaction():
                product = await conn.fetchrow(
                    "SELECT id, name, stock, version FROM products WHERE id = $1",
                    order.productId
                )

                if not product:
                    raise HTTPException(status_code=404, detail="Product not found")

                if product["stock"] < order.quantity:
                    await conn.execute(
                        "INSERT INTO orders (product_id, quantity_ordered, user_id, status) "
                        "VALUES ($1, $2, $3, 'FAILED_OUT_OF_STOCK')",
                        order.productId, order.quantity, order.userId
                    )
                    raise HTTPException(status_code=400, detail="Insufficient stock")

                current_version = product["version"]
                new_stock = product["stock"] - order.quantity
                new_version = current_version + 1

                # Conditional update — only succeeds if version hasn't changed since we read
                result = await conn.execute(
                    "UPDATE products SET stock = $1, version = $2 "
                    "WHERE id = $3 AND version = $4",
                    new_stock, new_version, order.productId, current_version
                )

                rows_updated = int(result.split()[-1])

                if rows_updated == 0:
                    print(f"⚔️  Version conflict attempt {attempt} — product {order.productId}")
                    await asyncio.sleep(0.01 * attempt)
                    continue

                order_id = await conn.fetchval(
                    "INSERT INTO orders (product_id, quantity_ordered, user_id, status) "
                    "VALUES ($1, $2, $3, 'SUCCESS') RETURNING id",
                    order.productId, order.quantity, order.userId
                )

                return {
                    "orderId": order_id,
                    "productId": order.productId,
                    "quantityOrdered": order.quantity,
                    "stockRemaining": new_stock,
                    "newVersion": new_version,
                }

    # All retries exhausted — record conflict failure
    pool2 = await get_pool()
    await pool2.execute(
        "INSERT INTO orders (product_id, quantity_ordered, user_id, status) "
        "VALUES ($1, $2, $3, 'FAILED_CONFLICT')",
        order.productId, order.quantity, order.userId
    )
    raise HTTPException(
        status_code=409,
        detail="Failed to place order due to concurrent modification. Please try again."
    )


# ---------------------------------------------------------------------------
# GET /api/orders/stats
# ---------------------------------------------------------------------------
@router.get("/stats")
async def get_stats():
    pool = await get_pool()
    row = await pool.fetchrow("""
        SELECT
            COUNT(*)                                          AS total_orders,
            COUNT(*) FILTER (WHERE status = 'SUCCESS')       AS successful_orders,
            COUNT(*) FILTER (WHERE status = 'FAILED_OUT_OF_STOCK') AS failed_out_of_stock,
            COUNT(*) FILTER (WHERE status = 'FAILED_CONFLICT')     AS failed_conflict
        FROM orders
    """)
    return {
        "totalOrders":      int(row["total_orders"]),
        "successfulOrders": int(row["successful_orders"]),
        "failedOutOfStock": int(row["failed_out_of_stock"]),
        "failedConflict":   int(row["failed_conflict"]),
    }
