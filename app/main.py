from fastapi import FastAPI

from app.api.routes import health, items

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(items.router)
