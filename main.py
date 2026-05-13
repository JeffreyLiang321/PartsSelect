"""
FastAPI server, our single entry point for the PartSelect agent.

Endpoints:
  POST /api/chat   — send a message, get a response
  GET  /api/health — sanity check

Run via: uvicorn main:app --reload --port 8000
"""

import asyncio
import threading
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agent.loop import AgentCancelled, run_agent

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
async def chat(payload: ChatRequest, request: Request):
    """
    Accept full conversation history -> return agent's next reply.

    Frontend should maintain message history and
    sending it on every request. I'll keep the backend fully stateless —
    no session storage, no database writes per turn.

    Keeps the server simple and horizontally scalable.

    Client-disconnect cancellation:
      The sync agent loop runs in a worker thread (so it doesn't block the
      event loop), while the request task polls request.is_disconnected().
      If the browser aborts (user clicked the Stop icon), we set a
      threading.Event the agent checks between iterations / tool calls, so
      it bails at the next safe boundary instead of burning more tokens.
    """
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages array cannot be empty")

    messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    cancel_event = threading.Event()

    agent_task = asyncio.create_task(
        asyncio.to_thread(run_agent, messages, cancel_event)
    )
    watcher_task = asyncio.create_task(_watch_disconnect(request, cancel_event))

    try:
        done, _ = await asyncio.wait(
            {agent_task, watcher_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if agent_task in done:
            try:
                reply, parts = agent_task.result()
            except AgentCancelled:
                print("[chat] agent cancelled by client disconnect")
                # 499 = client closed request (nginx convention). The client
                # is already gone, so the body is largely informational.
                raise HTTPException(status_code=499, detail="Client cancelled request")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
            return ChatResponse(reply=reply, parts=parts)

        # Watcher fired first: client disconnected. Signal the agent to bail
        # and wait briefly for a clean exit so we don't leak the thread.
        cancel_event.set()
        try:
            await asyncio.wait_for(agent_task, timeout=5.0)
        except (asyncio.TimeoutError, AgentCancelled, Exception):
            pass
        print("[chat] client disconnected mid-request, agent cancelled")
        raise HTTPException(status_code=499, detail="Client cancelled request")
    finally:
        watcher_task.cancel()
        if not agent_task.done():
            cancel_event.set()


async def _watch_disconnect(request: Request, cancel_event: threading.Event) -> None:
    """
    Poll the underlying ASGI receive channel until the client disconnects,
    then return. Polling interval is small enough to feel responsive but
    not so tight that it wastes CPU.
    """
    while True:
        if await request.is_disconnected():
            cancel_event.set()
            return
        await asyncio.sleep(0.25)


@app.get("/api/health")
async def health():
    return {"status": "ok"}