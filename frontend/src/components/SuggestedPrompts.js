// Example questions shown before the first message, so visitors who don't
// know a part or model number can see what the agent does in one click.
// Each one exercises a different tool path.
const PROMPTS = [
  "My dishwasher isn't draining. What should I check?",
  'How do I install part PS11752778?',
  'Is PS11752778 compatible with model WDT780SAEM1?',
  'What parts fit refrigerator model WRT311FZDB00?',
];

function SuggestedPrompts({ onSelect }) {
  return (
    <div className="suggested-prompts">
      <div className="suggested-prompts-inner">
        <span className="suggested-prompts-label">Not sure what to ask? Try one:</span>
        {PROMPTS.map((prompt) => (
          <button key={prompt} type="button" className="chip" onClick={() => onSelect(prompt)}>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export default SuggestedPrompts;
