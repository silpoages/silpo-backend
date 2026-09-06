from fastapi import FastAPI

from app.api.routes import auth, health, templates

app = FastAPI(title="Silpo Backend")

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(templates.router)
