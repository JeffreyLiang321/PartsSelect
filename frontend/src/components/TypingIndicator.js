import React from 'react';

function TypingIndicator() {
  return (
    <div className="message-row agent">
      <div className="avatar">P</div>
      <div className="bubble-wrapper">
        <div className="bubble agent typing-bubble">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  );
}

export default TypingIndicator;
