from fastapi import FastAPI

from app.api.routes import emergency_contacts, health, templates

app = FastAPI(title="Silpo Backend")

app.include_router(health.router)
app.include_router(templates.router)
app.include_router(emergency_contacts.router)
