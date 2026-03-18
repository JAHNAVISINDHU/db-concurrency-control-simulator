from fastapi import APIRouter, HTTPException
from app.db.pool import get_pool

router = APIRouter()


@router.get("/{product_id}")
async def get_product(product_id: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, stock, version FROM products WHERE id = $1",
        product_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return dict(row)


@router.post("/reset")
async def reset_inventory():
    pool = await get_pool()
    await pool.execute("""
        UPDATE products SET
            stock = CASE
                WHEN id = 1 THEN 100
                WHEN id = 2 THEN 50
                WHEN id = 3 THEN 200
                ELSE stock
            END,
            version = 1
    """)
    await pool.execute("DELETE FROM orders")
    return {"message": "Product inventory reset successfully."}
