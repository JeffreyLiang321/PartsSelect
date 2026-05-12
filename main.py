"""
FastAPI server, our single entry point for the PartSelect agent.

Endpoints:
  POST /api/chat   — send a message, get a response
  GET  /api/health — sanity check

Run via: uvicorn main:app --reload --port 8000
"""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agent.loop import run_agent

app = FastAPI(title="PartSelect Agent API")

# CORS — allow Next.js dev server and production origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js dev
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Schemas

class Message(BaseModel):
    role: str      # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


class ChatResponse(BaseModel):
    reply: str
    parts: list[dict[str, Any]] = []


# Endpoints

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Accept full conversation history -> return agent's next reply.

    Frontend should maintain message history and
    sending it on every request. I'll keep the backend fully stateless —
    no session storage, no database writes per turn.

    Keeps the server simple and horizontally scalable.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages array cannot be empty")

    # Convert Pydantic models to plain dicts for the agent loop
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    try:
        reply, parts = run_agent(messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    return ChatResponse(reply=reply, parts=parts)


@app.get("/api/health")
async def health():
    return {"status": "ok"}