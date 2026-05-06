/**
 * Personality selector - pick which AI voice to chat with.
 *
 * Controlled single-select. The host provides the personality list
 * and handles selection. Supports a "no personality" / default mode.
 */

import type { Personality } from "../chat-types";

export interface PersonalitySelectorProps {
  personalities: Personality[];
  selectedId: string | null;
  onSelect: (personalityId: string | null) => void;
  /** Label for the "default / no personality" option. */
  defaultLabel?: string;
  className?: string;
}

export function PersonalitySelector({
  personalities,
  selectedId,
  onSelect,
  defaultLabel,
  className,
}: PersonalitySelectorProps) {
  return (
    <div className={`nexo-personality-selector ${className ?? ""}`} role="listbox">
      {defaultLabel && (
        <button
          type="button"
          role="option"
          aria-selected={selectedId === null}
          className={`nexo-personality-option ${selectedId === null ? "is-selected" : ""}`}
          onClick={() => onSelect(null)}
        >
          <div className="nexo-personality-option__avatar nexo-personality-option__avatar--default" />
          <span className="nexo-personality-option__name">{defaultLabel}</span>
        </button>
      )}
      {personalities.map((p) => (
        <PersonalityOption
          key={p.id}
          personality={p}
          selected={selectedId === p.id}
          onSelect={() => onSelect(p.id)}
        />
      ))}
    </div>
  );
}

export interface PersonalityOptionProps {
  personality: Personality;
  selected: boolean;
  onSelect: () => void;
  className?: string;
}

export function PersonalityOption({ personality, selected, onSelect, className }: PersonalityOptionProps) {
  const avatar = personality.assets.avatarSmall ?? personality.assets.avatarLight;
  const brandColor = personality.brand.primaryColor;

  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      className={`nexo-personality-option ${selected ? "is-selected" : ""} ${className ?? ""}`}
      style={brandColor ? { "--nexo-personality-accent": brandColor } as React.CSSProperties : undefined}
      onClick={onSelect}
    >
      {avatar ? (
        <img className="nexo-personality-option__avatar" src={avatar} alt="" width={32} height={32} />
      ) : (
        <div
          className="nexo-personality-option__avatar nexo-personality-option__avatar--fallback"
          style={brandColor ? { backgroundColor: brandColor } : undefined}
        >
          {personality.name.charAt(0).toUpperCase()}
        </div>
      )}
      <div className="nexo-personality-option__info">
        <span className="nexo-personality-option__name">{personality.name}</span>
        {personality.description && (
          <span className="nexo-personality-option__desc">{personality.description}</span>
        )}
      </div>
    </button>
  );
}
