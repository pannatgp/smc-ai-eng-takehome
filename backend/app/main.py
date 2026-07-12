from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.db import Base, engine
from app.models import Message, User, VectorRegistry  # noqa: F401 (register models before create_all)

app = FastAPI(title="Financial Q&A Chatbot")

app.add_middleware(
    CORSMiddleware,
    # Accept the Vite dev server on any localhost/127.0.0.1 port. Vite falls back to
    # 5174, 5175, ... when 5173 is taken, and localhost vs 127.0.0.1 are distinct
    # origins — pinning a single one silently breaks auth with a CORS error.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # `financial_data` is owned by the provided SQL dump (loaded via docker-entrypoint-initdb.d).
    # `users`/`messages` are owned by the app, so we bootstrap them here.
    Base.metadata.create_all(bind=engine)


app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
