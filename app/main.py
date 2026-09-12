from fastapi import FastAPI

from app.api.routes import auth, emergency_contacts, health, mood_logs, users

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(mood_logs.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(emergency_contacts.router)
