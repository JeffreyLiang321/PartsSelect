import { useState, useEffect, useRef } from 'react';
import './App.css';
import Header from './components/Header';
import ChatWindow from './components/ChatWindow';
import InputBar from './components/InputBar';
import { sendMessage } from './api/api';

const SESSION_KEY = 'partselect_messages';

// Must stay within the backend's limits (main.py)
const MAX_HISTORY = 20;
const MAX_ASSISTANT_CHARS = 8000;

function errorText(err) {
  switch (err.status) {
    case 429:
      return err.message || "You're sending messages too quickly. Please wait a bit and try again.";
    case 422:
      return 'That message is too long. Please keep questions under 1,000 characters.';
    case 502:
    case 503:
    case 504:
      return 'The demo server is waking up. Please try again in a minute.';
    default:
      return 'Sorry, I ran into an issue. Please try again.';
  }
}

const WELCOME_MESSAGE = {
  role: 'assistant',
  content: `Hi! I'm the PartSelect Parts Assistant. I can help you:
- **Find parts** by part number or model number
- **Diagnose symptoms** — describe what's wrong and I'll suggest parts
- **Check compatibility** — tell me your model number and a part number
- **Get repair guides** — step-by-step instructions for common fixes

I specialize in **refrigerator** and **dishwasher** parts. What can I help you with?`,
  parts: [],
};

function loadSession() {
  try {
    const saved = sessionStorage.getItem(SESSION_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {}
  return [WELCOME_MESSAGE];
}

function App() {
  const [messages, setMessages] = useState(loadSession);
  const [isLoading, setIsLoading] = useState(false);
  const [applianceType, setApplianceType] = useState(null);
  const abortControllerRef = useRef(null);

  // Derive from messages -> no separate state needed
  // const hasStarted = messages.some((m) => m.role === 'user');

  useEffect(() => {
    try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(messages)); } catch {}
  }, [messages]);

  const handleSend = async (text) => {
    if (!text.trim() || isLoading) return;

    const content = applianceType
      ? `[${applianceType.charAt(0).toUpperCase() + applianceType.slice(1)}] ${text}`
      : text;

    const userMessage = { role: 'user', content };
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      // Stop markers and error notices are UI-only; the backend also caps
      // history length, so send only the most recent turns.
      const payload = nextMessages
        .filter((m) => !m.isStopped && !m.isError)
        .slice(-MAX_HISTORY)
        .map(({ role, content }) => ({
          role,
          content: role === 'assistant' ? content.slice(0, MAX_ASSISTANT_CHARS) : content,
        }));
      const data = await sendMessage(payload, controller.signal);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, parts: data.parts || [] },
      ]);
    } catch (err) {
      if (err.name === 'AbortError') {
        // Keep the user's question visible and leave a clear stop marker
        // so they can see what happened and ask something new.
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: 'Response stopped.',
            isStopped: true,
            parts: [],
          },
        ]);
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: errorText(err),
          isError: true,
          parts: [],
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
  };

  const handleClear = () => {
    setMessages([WELCOME_MESSAGE]);
    setIsLoading(false);
    setApplianceType(null);
    try { sessionStorage.removeItem(SESSION_KEY); } catch {}
  };

  return (
    <div className="app">
      <Header onClear={handleClear} />
      <ChatWindow messages={messages} isLoading={isLoading} onSend={handleSend} />
      <InputBar
        onSend={handleSend}
        onStop={handleStop}
        isLoading={isLoading}
        applianceType={applianceType}
        onApplianceChange={setApplianceType}
      />
    </div>
  );
}

export default App;
