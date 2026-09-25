import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from document_chat.config import config
from document_chat.logging import configure_logging
from document_chat.routers.conversations import router as conversations_router
from document_chat.routers.documents import router as documents_router

configure_logging()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in config.cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)
app.include_router(conversations_router)


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)
