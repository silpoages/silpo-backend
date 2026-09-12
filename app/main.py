from fastapi import FastAPI

from app.api.routes import health, users

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(users.router)
