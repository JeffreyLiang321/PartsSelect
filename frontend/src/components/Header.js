import { useState } from 'react';

function Header({ onClear }) {
  const [showConfirm, setShowConfirm] = useState(false);

  const handleConfirm = () => {
    setShowConfirm(false);
    onClear();
  };

  return (
    <>
      <header className="header">
        <div className="header-left">
          <img
            src="/partselect-complete-logo.png"
            alt="PartSelect"
            className="header-logo"
          />
          <span className="header-tagline">Parts Assistant</span>
        </div>
        <div className="header-right">
          <img
            src="/status_info.png"
            alt="Support: 1-866-319-8402 Mon–Sat 8am–8pm EST"
            className="header-status-img"
          />
          <button className="header-clear-btn" onClick={() => setShowConfirm(true)}>
            New conversation
          </button>
        </div>
      </header>

      {showConfirm && (
        <div className="modal-overlay" onClick={() => setShowConfirm(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <p className="modal-title">Start a new conversation?</p>
            <p className="modal-body">Your current chat will be cleared.</p>
            <div className="modal-actions">
              <button className="modal-btn-cancel" onClick={() => setShowConfirm(false)}>
                Cancel
              </button>
              <button className="modal-btn-confirm" onClick={handleConfirm}>
                Start New
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default Header;
