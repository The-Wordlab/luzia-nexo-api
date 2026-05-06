/**
 * Floating action button that opens the chat panel.
 *
 * Only renders in standalone mode (browser). Hidden in webview mode
 * where the native app owns the chat chrome.
 *
 * Supports a custom avatar image (character icon) or falls back to a
 * generic chat bubble. The Luzia octopus is the recommended default.
 */

import { useState } from "react";
import type { AgentChatOptions, Personality } from "../chat-types";

export interface AgentChatFabProps {
  /** Agent chat connection options. */
  chatOptions: AgentChatOptions;
  /** The personality to show in the chat panel. */
  personality?: Personality;
  /** Shell mode: "standalone" shows the FAB, "webview" hides it. */
  shellMode: "standalone" | "webview";
  /** Lazy-loaded chat panel render function. */
  renderPanel: (props: {
    chatOptions: AgentChatOptions;
    personality?: Personality;
    onClose: () => void;
  }) => React.ReactNode;
  /** Accessible label for the FAB button. Required - host provides translation. */
  ariaLabel: string;
  /** Optional visible label shown on larger screens. */
  label?: string;
  /**
   * Custom avatar for the FAB button. Can be:
   * - A URL to an image (PNG, SVG, etc.)
   * - An emoji string (rendered as text)
   * - undefined (falls back to default chat bubble icon)
   */
  avatar?: string;
  /** Override class. */
  className?: string;
}

function isUrl(s: string): boolean {
  return s.startsWith("http") || s.startsWith("/") || s.startsWith("data:");
}

function FabIcon({ avatar }: { avatar?: string }) {
  if (!avatar) {
    // Default: chat bubble icon
    return (
      <svg className="nexo-chat-fab__icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    );
  }

  if (isUrl(avatar)) {
    return <img className="nexo-chat-fab__avatar" src={avatar} alt="" />;
  }

  // Emoji or short text
  return <span className="nexo-chat-fab__emoji">{avatar}</span>;
}

export function AgentChatFab({
  chatOptions,
  personality,
  shellMode,
  renderPanel,
  ariaLabel,
  label,
  avatar,
  className,
}: AgentChatFabProps) {
  const [open, setOpen] = useState(false);

  // Resolve avatar: prop > personality assets > undefined (fallback to icon)
  const resolvedAvatar =
    avatar ??
    personality?.assets?.avatarLight ??
    undefined;

  // Hidden in webview mode - native app owns chat
  if (shellMode === "webview") return null;

  return (
    <>
      {open && (
        <div className="nexo-chat-overlay" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          {renderPanel({ chatOptions, personality, onClose: () => setOpen(false) })}
        </div>
      )}
      <button
        type="button"
        className={`nexo-chat-fab ${resolvedAvatar ? "nexo-chat-fab--avatar" : ""} ${className ?? ""}`}
        onClick={() => setOpen(true)}
        aria-label={ariaLabel}
      >
        <FabIcon avatar={resolvedAvatar} />
        {/* Pill text: label prop wins, then personality name, then nothing */}
        {resolvedAvatar && (label || personality?.name) && (
          <span className="nexo-chat-fab__name">{label || personality?.name}</span>
        )}
        {!resolvedAvatar && label ? <span className="nexo-chat-fab__label">{label}</span> : null}
      </button>
    </>
  );
}
