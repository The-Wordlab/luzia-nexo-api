/**
 * Floating action button that opens the chat panel.
 *
 * Only renders in standalone mode (browser). Hidden in webview mode
 * where the native app owns the chat chrome.
 *
 * Supports a custom avatar image (character icon) with the personality
 * name shown alongside in a pill shape.
 */

import { useState } from "react";
import type {
  AgentAppearance,
  AgentChatOptions,
  Personality,
} from "../chat-types";

export interface AgentChatFabProps {
  /** Agent chat connection options. */
  chatOptions: AgentChatOptions;
  /** The personality to show in the chat panel. */
  personality?: Personality;
  /** Bootstrap-resolved per-user appearance overrides. */
  agentAppearance?: AgentAppearance;
  /** Shell mode: "standalone" shows the FAB, "webview" hides it. */
  shellMode: "standalone" | "webview";
  /** Lazy-loaded chat panel render function. */
  renderPanel: (props: {
    chatOptions: AgentChatOptions;
    personality?: Personality;
    agentAppearance?: AgentAppearance;
    onClose: () => void;
  }) => React.ReactNode;
  /** Accessible label for the FAB button. Required - host provides translation. */
  ariaLabel: string;
  /** Optional visible label shown on larger screens. */
  label?: string;
  /**
   * Custom avatar for the FAB button. Can be:
   * - A URL to an image (PNG, SVG, etc.)
   * - An emoji string
   * - undefined (falls back to personality assets, then default icon)
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
    return (
      <svg
        className="nexo-chat-fab__icon"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
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
  agentAppearance,
  shellMode,
  renderPanel,
  ariaLabel,
  label,
  avatar,
  className,
}: AgentChatFabProps) {
  const [open, setOpen] = useState(false);

  const resolvedAvatar =
    avatar ??
    agentAppearance?.avatarLight ??
    agentAppearance?.avatarSmall ??
    agentAppearance?.avatarStatic ??
    personality?.assets?.avatarLight ??
    personality?.assets?.avatarSmall ??
    personality?.assets?.avatarStatic ??
    undefined;
  const resolvedName =
    agentAppearance?.displayName ??
    personality?.name ??
    label;

  if (shellMode === "webview") return null;

  return (
    <>
      {open && (
        <div className="nexo-chat-overlay" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          {renderPanel({
            chatOptions,
            personality,
            agentAppearance,
            onClose: () => setOpen(false),
          })}
        </div>
      )}
      <button
        type="button"
        className={`nexo-chat-fab ${resolvedAvatar ? "nexo-chat-fab--avatar" : ""} ${className ?? ""}`}
        onClick={() => setOpen(true)}
        aria-label={ariaLabel}
      >
        <FabIcon avatar={resolvedAvatar} />
        {resolvedAvatar && resolvedName ? (
          <span className="nexo-chat-fab__name">{resolvedName}</span>
        ) : null}
        {!resolvedAvatar && label ? <span className="nexo-chat-fab__label">{label}</span> : null}
      </button>
    </>
  );
}
