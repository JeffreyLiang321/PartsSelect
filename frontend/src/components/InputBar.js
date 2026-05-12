import { useState, useRef, useEffect } from 'react';

function InputBar({ onSend, isLoading, applianceType, onApplianceChange }) {
  const [input, setInput] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize: grow up to 200px, then scroll internally
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  }, [input]);

  const canSend = input.trim().length > 0 && !isLoading;

  const handleSend = () => {
    if (!canSend) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleAppliance = (type) => {
    onApplianceChange(applianceType === type ? null : type);
  };

  const placeholder = isLoading
    ? 'Waiting for response...'
    : applianceType
    ? `Ask about your ${applianceType}…`
    : 'Ask about parts, compatibility, or repairs…';

  return (
    <div className="input-bar">
      <div className="input-bar-inner">

        <div className="appliance-toggle">
          <button
            className={`appliance-btn${applianceType === 'refrigerator' ? ' active' : ''}`}
            onClick={() => toggleAppliance('refrigerator')}
          >
            Refrigerator
          </button>
          <button
            className={`appliance-btn${applianceType === 'dishwasher' ? ' active' : ''}`}
            onClick={() => toggleAppliance('dishwasher')}
          >
            Dishwasher
          </button>
        </div>

        {/* Expanding message box — flex column so padding is uniform */}
        <div className="input-box-wrap">
          <textarea
            ref={textareaRef}
            className="input-field"
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isLoading}
          />
          <div className="input-box-footer">
            <button
              className="send-button"
              onClick={handleSend}
              disabled={!canSend}
              title="Send (Enter)"
            >
              Send ↑
            </button>
          </div>
        </div>

      </div>

      <p className="input-disclaimer">
        Parts AI can make mistakes, please verify responses via the{' '}
        <a href="https://www.partselect.com" target="_blank" rel="noopener noreferrer">
          PartSelect product page
        </a>
        .
      </p>
    </div>
  );
}

export default InputBar;
