from fastapi import FastAPI

from app.api.routes import health, templates, user

app = FastAPI(title="Silpo Backend")

app.include_router(user.router)
app.include_router(health.router)
app.include_router(templates.router)
