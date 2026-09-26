from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, emergency_contacts, health, mood_logs, users

app = FastAPI(title="Silpo Backend")

# Sem cookies/sessão (auth é via Bearer token no header), então liberar todas as
# origens não abre risco de CSRF; permite o app mobile rodar em modo web contra
# uma API local em outra origem (ex. Expo em :8081, API em :8000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(mood_logs.router)
app.include_router(users.router)
app.include_router(auth.router)
app.include_router(emergency_contacts.router)
