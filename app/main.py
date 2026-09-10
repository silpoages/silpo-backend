from fastapi import FastAPI

from app.api.routes import health, mood_logs, templates

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(templates.router)
app.include_router(mood_logs.router)
