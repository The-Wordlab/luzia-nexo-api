/**
 * Follow-up suggestion chips from a agent response.
 *
 * Rendered below the latest assistant message. Controlled - the host
 * provides the suggestions array and handles the click.
 */

export interface AgentSuggestionChipsProps {
  suggestions: string[];
  onSelect: (text: string) => void;
  disabled?: boolean;
  className?: string;
}

export function AgentSuggestionChips({ suggestions, onSelect, disabled, className }: AgentSuggestionChipsProps) {
  if (suggestions.length === 0) return null;

  return (
    <div className={`nexo-suggestion-chips ${className ?? ""}`}>
      {suggestions.map((text) => (
        <button
          key={text}
          type="button"
          className="nexo-suggestion-chip"
          disabled={disabled}
          onClick={() => onSelect(text)}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
