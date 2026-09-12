from fastapi import FastAPI

from app.api.routes import health, mood_logs, users

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(users.router)
app.include_router(mood_logs.router)
