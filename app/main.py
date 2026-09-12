from fastapi import FastAPI

from app.api.routes import auth, health, users

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(users.router)
app.include_router(auth.router)
