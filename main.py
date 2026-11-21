"""
FastAPI server, our single entry point for the PartSelect agent.

Endpoints:
  POST /api/chat   — send a message, get a response
  GET  /api/health — sanity check

Run via: uvicorn main:app --reload --port 8000
"""

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from backend.agent.loop import AgentCancelled, run_agent
from backend.rate_limit import RateLimiter, client_ip

logger = logging.getLogger("partselect")
logging.basicConfig(level=logging.INFO)

# Limits — public demo, so every request has a bounded cost
MAX_MESSAGES          = 20      # conversation turns sent per request
MAX_USER_CHARS        = 1000    # what a person types
MAX_ASSISTANT_CHARS   = 8000    # agent replies echoed back as history

rate_limiter = RateLimiter(
    per_ip_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "8")),
    per_ip_day=int(os.getenv("RATE_LIMIT_PER_DAY", "60")),
    global_day=int(os.getenv("RATE_LIMIT_GLOBAL_PER_DAY", "1500")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Warm up the vector collections at boot so the first visitor after a
    restart doesn't pay the load time. Failure here is logged, not fatal —
    the loaders retry lazily on first query anyway.
    """
    try:
        from backend.db import vector
        await asyncio.to_thread(vector._get_parts_collection)
        await asyncio.to_thread(vector._get_repairs_collection)
        await asyncio.to_thread(vector._get_blogs_collection)
        logger.info("warm-up complete")
    except Exception:
        logger.exception("warm-up failed; collections will load on first request")
    yield


app = FastAPI(title="PartSelect Agent API", lifespan=lifespan)

# CORS — browsers may only call us from these origins.
# Prod: ALLOWED_ORIGINS="https://<frontend>.vercel.app"
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
        if o.strip()
    ],
    allow_credentials=False,   # no cookies/auth — the API is anonymous
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# Schemas

class Message(BaseModel):
    # Only conversational roles. "system"/"tool" are set server-side by the
    # agent loop and must never come from the client.
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_ASSISTANT_CHARS)

    @model_validator(mode="after")
    def _cap_user_length(self):
        if self.role == "user" and len(self.content) > MAX_USER_CHARS:
            raise ValueError(f"user messages are limited to {MAX_USER_CHARS} characters")
        return self


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=MAX_MESSAGES)


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
    allowed, retry_after, reason = rate_limiter.check(
        client_ip(request.headers, request.client.host if request.client else None)
    )
    if not allowed:
        logger.warning("rate limited (%s)", reason)
        raise HTTPException(
            status_code=429,
            detail="You're sending messages too quickly. Please wait a bit and try again.",
            headers={"Retry-After": str(retry_after)},
        )

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
                logger.info("agent cancelled by client disconnect")
                # 499 = client closed request (nginx convention). The client
                # is already gone, so the body is largely informational.
                raise HTTPException(status_code=499, detail="Client cancelled request")
            except Exception:
                # Full traceback stays in server logs; the client gets nothing
                # that reveals paths, library versions or upstream API errors.
                logger.exception("agent error")
                raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
            return ChatResponse(reply=reply, parts=parts)

        # Watcher fired first: client disconnected. Signal the agent to bail
        # and wait briefly for a clean exit so we don't leak the thread.
        cancel_event.set()
        try:
            await asyncio.wait_for(agent_task, timeout=5.0)
        except (asyncio.TimeoutError, AgentCancelled, Exception):
            pass
        logger.info("client disconnected mid-request, agent cancelled")
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