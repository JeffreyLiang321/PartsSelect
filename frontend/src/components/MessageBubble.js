import { useState, useRef, useEffect } from 'react';
import { marked } from 'marked';

// YouTube helpers

const YT_RE =
  /https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?(?:[^#\s]*&)?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})[^\s)]*/g;

function extractYouTubeVideos(text) {
  const videos = [];
  const seen = new Set();
  let match;
  const re = new RegExp(YT_RE.source, 'g');
  while ((match = re.exec(text)) !== null) {
    const videoId = match[1];
    if (!seen.has(videoId)) {
      seen.add(videoId);
      // Check ~80 chars before the URL for install/repair context
      const fullText = text.toLowerCase();
      const isInstall = fullText.includes('install') || fullText.includes('how to replace');
      videos.push({ videoId, url: match[0], label: "Watch Guide"});
    }
  }
  return videos;
}

// PS chip injection

function addPSChips(html) {
  // Split on anchor tags so we don't chip PS numbers already inside links
  const segments = html.split(/(<a\b[^>]*>[\s\S]*?<\/a>)/gi);
  return segments
    .map((seg, i) => {
      if (i % 2 === 1) return seg; // inside <a> — leave alone
      return seg.replace(
        /\b(PS\d{5,})\b/g,
        '<span class="ps-chip" title="Ask about $1">$1</span>',
      );
    })
    .join('');
}

// Difficulty rank

const DIFFICULTY_COLORS = {
  'Really Easy': '#2e7d32',
  'Easy':        '#2e7d32',
  'Moderate':    '#e65100',
  'Hard':        '#c62828',
  'Very Hard':   '#c62828',
};

function difficultyColor(label) {
  return DIFFICULTY_COLORS[label] || '#555555';
}

// Sub-components

function PartCard({ part }) {
  return (
    <div className="part-card-rich">
      {part.image_url && (
        <img src={part.image_url} alt={part.part_name || 'Part'} className="part-img" />
      )}
      <div className="part-card-info">
        {part.part_name && (
          <div className="part-card-name">{part.part_name}</div>
        )}
        <div className="part-card-meta">
          {part.part_price != null && (
            <span className="part-price">${Number(part.part_price).toFixed(2)}</span>
          )}
          {part.in_stock != null && (
            <span className={`stock-badge ${part.in_stock ? 'in-stock' : 'out-of-stock'}`}>
              {part.in_stock ? 'In Stock' : 'Out of Stock'}
            </span>
          )}
          {part.install_difficulty && (
            <span
              className="difficulty-badge"
              style={{ color: difficultyColor(part.install_difficulty) }}
            >
              {part.install_difficulty}
            </span>
          )}
        </div>
      </div>
      {part.product_url && (
        <a
          href={part.product_url}
          target="_blank"
          rel="noopener noreferrer"
          className="part-card-link"
        >
          View Part →
        </a>
      )}
    </div>
  );
}

function VideoCard({ url, videoId, label='Watch Repair Guide' }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="video-card">
      <div className="video-thumb-wrap">
        <img
          src={`https://img.youtube.com/vi/${videoId}/mqdefault.jpg`}
          alt="Repair guide video"
          className="video-thumb"
        />
        <div className="video-play-overlay">▶</div>
      </div>
      <span className="video-label">{label}</span>
    </a>
  );
}

// Main component

function MessageBubble({ message, isFirst, onSend }) {
  const { role, content, isError, isStopped, parts = [] } = message;
  const [copied, setCopied] = useState(false);
  const bubbleRef = useRef(null);

  // Event delegation for PS chip clicks
  useEffect(() => {
    const el = bubbleRef.current;
    if (!el || !onSend) return;
    const handler = (e) => {
      const chip = e.target.closest('.ps-chip');
      if (chip) onSend(`Tell me about ${chip.textContent.trim()}`);
    };
    el.addEventListener('click', handler);
    return () => el.removeEventListener('click', handler);
  }, [onSend]);

  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  if (role === 'user') {
    return (
      <div className="message-row user">
        <div className="bubble-wrapper">
          <div className="bubble user">{content}</div>
        </div>
      </div>
    );
  }

  // Stopped marker — slim inline indicator, no avatar/copy
  if (isStopped) {
    return (
      <div className="stopped-row" role="status">
        <svg
          width="12"
          height="12"
          viewBox="0 0 14 14"
          aria-hidden="true"
          focusable="false"
        >
          <rect x="2" y="2" width="10" height="10" rx="1.5" fill="currentColor" />
        </svg>
        <span>{content || 'Response stopped.'}</span>
      </div>
    );
  }

  // Agent message
  const bubbleClass = [
    'bubble agent',
    isFirst ? 'welcome' : '',
    isError ? 'error' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const html = addPSChips(marked(content, { breaks: true }));
  const videos = isError ? [] : extractYouTubeVideos(content);

  // mirror system prompt rule to avoid overwhelming users with too many parts if no model number is given
  const hasModelNumber = content.match(/\b[A-Z]{2,}[\dA-Z]{4,}\b/);
  const uniqueBrands = new Set(parts.map((p) => p.brand).filter(Boolean));
  // const displayParts = !hasModelNumber && uniqueBrands.size > 3 ? parts.slice(0, 3) : parts;
  const mentionedParts = parts.filter(p => content.includes(p.part_id));
  const displayParts = mentionedParts.length > 0 ? mentionedParts : (
    (!hasModelNumber && uniqueBrands.size > 3 ? parts.slice(0, 3) : parts)
  );

  return (
    <div className="message-row agent">
      <div className="avatar">P</div>
      <div className="bubble-wrapper">
        <div
          ref={bubbleRef}
          className={bubbleClass}
          dangerouslySetInnerHTML={{ __html: html }}
        />
        {videos.map(({ url, videoId, label }) => (
          <VideoCard key={videoId} url={url} videoId={videoId} label={label} />
        ))}
        {displayParts.map((part) => (
          <PartCard key={part.part_id} part={part} />
        ))}
      </div>
      {!isError && (
        <button className="copy-btn" onClick={handleCopy} title="Copy message">
          {copied ? '✓' : '⧉'}
        </button>
      )}
    </div>
  );
}

export default MessageBubble;
