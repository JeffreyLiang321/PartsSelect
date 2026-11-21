// Backend URL: override with REACT_APP_API_URL; otherwise the Hugging Face
// Space in production builds and the local FastAPI server in development.
const API_BASE =
  process.env.REACT_APP_API_URL ||
  (process.env.NODE_ENV === 'production'
    ? 'https://jeffjeff20120112-partselect-agent.hf.space'
    : 'http://localhost:8000');

export class ApiError extends Error {
  constructor(status, message) {
    super(message || `API error: ${status}`);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function sendMessage(messages, signal) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!res.ok) {
    // Backend sends a human-readable `detail` string for 429/500
    let detail = null;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return await res.json();
}
