import { useState, useEffect } from 'react';
import './App.css';
import Header from './components/Header';
import ChatWindow from './components/ChatWindow';
import InputBar from './components/InputBar';
import { sendMessage } from './api/api';

const SESSION_KEY = 'partselect_messages';

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

    try {
      const data = await sendMessage(nextMessages);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.reply, parts: data.parts || [] },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I ran into an issue. Please try again.',
          isError: true,
          parts: [],
        },
      ]);
    } finally {
      setIsLoading(false);
    }
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
        isLoading={isLoading}
        applianceType={applianceType}
        onApplianceChange={setApplianceType}
      />
    </div>
  );
}

export default App;
