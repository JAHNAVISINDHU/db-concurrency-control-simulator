# 🗄️ db-concurrency-control-simulator
 
**Database Concurrency Control Simulator for Inventory Management**
Built with **Python 3.12 + FastAPI + asyncpg + PostgreSQL 15**, fully containerized with Docker.
 
Demonstrates and compares **pessimistic locking** (`SELECT FOR UPDATE`) vs **optimistic locking** (version-based conflict detection) for handling concurrent inventory orders.
 
> **Author:** [JAHNAVI SINDHU](https://github.com/JAHNAVISINDHU)
 
---
 
## 📁 Project Structure
 
```
db-concurrency-simulator/
├── docker-compose.yml          # Multi-service orchestration
├── Dockerfile                  # Python app container
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── .gitignore
├── concurrent-test.sh          # Concurrent load test script
├── monitor-locks.sh            # Real-time DB lock monitor
├── seeds/
│   └── init.sql                # DB schema + seed data
└── app/
    ├── main.py                 # FastAPI app entry point
    ├── db/
    │   └── pool.py             # asyncpg connection pool
    └── routes/
        ├── products.py         # GET product, POST reset
        └── orders.py           # pessimistic, optimistic, stats
```
 
---
 
## ⚡ Quick Start
 
### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) v20+
- `curl` and `bash` for testing
 
### 1. Clone the repository
```bash
git clone https://github.com/JAHNAVISINDHU/db-concurrency-control-simulator.git
cd db-concurrency-control-simulator
```
 
### 2. Set up environment
```bash
cp .env.example .env
```
 
### 3. Build and start
```bash
docker-compose up --build
```
 
Wait until you see:
```
inventory_app | ✅ Database connection pool established
inventory_app | INFO:     Application startup complete.
inventory_app | INFO:     Uvicorn running on http://0.0.0.0:8080
```
 
### 4. Verify
```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/products/1
```
 
Expected:
```json
{"id": 1, "name": "Super Widget", "stock": 100, "version": 1}
```
 
### 5. Interactive API Docs (Swagger UI)
```
http://localhost:8080/docs
```
 
### 6. Stop
```bash
docker-compose down
 
# Stop AND wipe the database volume (full reset)
docker-compose down -v
```
 
---
 
## 🌐 API Reference
 
### Health
```bash
GET  /health
```
 
### Products
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/products/{id}` | Get product by ID |
| POST | `/api/products/reset` | Reset all stock + clear orders |
 
```bash
# Get product 1
curl http://localhost:8080/api/products/1
 
# Reset all inventory
curl -X POST http://localhost:8080/api/products/reset
```
 
**404 response:**
```json
{"detail": "Product not found"}
```
 
---
 
### Orders
 
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/orders/pessimistic` | Order with row-level lock |
| POST | `/api/orders/optimistic` | Order with version conflict detection |
| GET | `/api/orders/stats` | Count orders by status |
 
#### Place a pessimistic order
```bash
curl -X POST http://localhost:8080/api/orders/pessimistic \
  -H "Content-Type: application/json" \
  -d '{"productId": 1, "quantity": 10, "userId": "user-1"}'
```
**201:**
```json
{"orderId": 1, "productId": 1, "quantityOrdered": 10, "stockRemaining": 90}
```
 
#### Place an optimistic order
```bash
curl -X POST http://localhost:8080/api/orders/optimistic \
  -H "Content-Type: application/json" \
  -d '{"productId": 1, "quantity": 10, "userId": "user-2"}'
```
**201:**
```json
{"orderId": 2, "productId": 1, "quantityOrdered": 10, "stockRemaining": 80, "newVersion": 3}
```
 
#### Trigger insufficient stock (400)
```bash
curl -X POST http://localhost:8080/api/orders/pessimistic \
  -H "Content-Type: application/json" \
  -d '{"productId": 1, "quantity": 9999, "userId": "user-3"}'
```
**400:**
```json
{"detail": "Insufficient stock"}
```
 
#### Trigger version conflict (409) — optimistic only
Send many concurrent requests. After 3 failed retries:
```json
{"detail": "Failed to place order due to concurrent modification. Please try again."}
```
 
#### Order statistics
```bash
curl http://localhost:8080/api/orders/stats
```
**200:**
```json
{"totalOrders": 20, "successfulOrders": 15, "failedOutOfStock": 3, "failedConflict": 2}
```
 
---
 
## 🔥 Concurrent Load Tests
 
```bash
# Make scripts executable (first time only)
chmod +x concurrent-test.sh monitor-locks.sh
 
# Test pessimistic locking — 20 concurrent requests
./concurrent-test.sh pessimistic
 
# Test optimistic locking — will show 409 conflicts under contention
./concurrent-test.sh optimistic
 
# Custom parameters
NUM_REQUESTS=50 QUANTITY=3 ./concurrent-test.sh optimistic
BASE_URL=http://myserver:8080 ./concurrent-test.sh pessimistic
```
 
### What to expect
 
| Strategy | Successes | 400s | 409s |
|---|---|---|---|
| **Pessimistic** | Up to stock/qty | When stock depleted | Never |
| **Optimistic** | Some succeed | When stock depleted | Some — retries exhausted |
 
---
 
## 🔒 Monitor Database Locks
 
Run in a **separate terminal** while tests are happening:
```bash
./monitor-locks.sh
```
 
To manually hold a lock and observe it:
```bash
# Terminal 1 — open psql and hold a lock
docker exec -it inventory_db psql -U inventory_user -d inventory_db
```
```sql
BEGIN;
SELECT * FROM products WHERE id = 1 FOR UPDATE;
-- Do NOT commit yet — lock is held
```
```bash
# Terminal 2 — watch the monitor show the lock
./monitor-locks.sh
```
```sql
-- Terminal 1 — release the lock
COMMIT;
```
 
---
 
## 🧠 Locking Strategies Explained
 
### Pessimistic (`SELECT FOR UPDATE`)
 
```sql
BEGIN;
SELECT * FROM products WHERE id = $1 FOR UPDATE;
-- ☝️ Row is now locked — all other sessions must WAIT here
UPDATE products SET stock = stock - $qty WHERE id = $1;
INSERT INTO orders ...;
COMMIT; -- lock released, next waiter proceeds
```
 
- ✅ Zero conflicts — correctness guaranteed regardless of contention
- ⚠️ High contention = requests queue up = lower throughput
 
### Optimistic (Version field)
 
```sql
-- 1. Read WITHOUT any lock
SELECT id, stock, version FROM products WHERE id = $1;
 
-- 2. Do business logic in application memory
 
-- 3. Update ONLY if version hasn't changed since we read
UPDATE products SET stock=$new, version=$v+1
WHERE id=$1 AND version=$current;
 
-- 4. If rowcount=0 → conflict → retry (max 3 attempts)
```
 
- ✅ No locks held = higher throughput at low/medium contention
- ⚠️ Under heavy contention → many 409 errors
 
---
 
## 🛠️ Troubleshooting
 
### Port 8080 already in use
```bash
# Change port in .env
API_PORT=3001
docker-compose up --build
```
 
### Tables don't exist / schema is wrong
PostgreSQL only runs `init.sql` on a **fresh volume**:
```bash
docker-compose down -v
docker-compose up --build
```
 
### App container exits — can't reach database
```bash
docker-compose logs app   # read the error
docker-compose restart app
```
 
### `Permission denied` on scripts
```bash
chmod +x concurrent-test.sh monitor-locks.sh
```
 
### Inspect the database directly
```bash
docker exec -it inventory_db psql -U inventory_user -d inventory_db
 
-- Useful queries:
SELECT * FROM products;
SELECT status, COUNT(*) FROM orders GROUP BY status;
SELECT * FROM orders ORDER BY created_at DESC LIMIT 20;
```
 
### Nuclear reset (wipe everything)
```bash
docker-compose down -v --remove-orphans
docker system prune -f
docker-compose up --build
```
 
---
 
## 📦 Environment Variables
 
| Variable | Default | Description |
|----------|---------|-------------|
| `DB_USER` | `inventory_user` | PostgreSQL username |
| `DB_PASSWORD` | `inventory_pass` | PostgreSQL password |
| `DB_NAME` | `inventory_db` | Database name |
| `DB_PORT` | `5432` | Exposed PostgreSQL port |
| `API_PORT` | `8080` | App HTTP port |
| `DATABASE_URL` | auto-constructed | Full connection string |
 
---
 
## 🧰 Tech Stack
 
| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | FastAPI |
| ASGI Server | Uvicorn |
| DB Driver | asyncpg (fully async) |
| Database | PostgreSQL 15 |
| Container | Docker + Docker Compose |
 
---
