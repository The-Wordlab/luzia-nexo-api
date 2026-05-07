/**
 * Chat message bubble.
 *
 * Renders a user or assistant message. Assistant messages can show a
 * personality avatar and brand color. Controlled - no fetching.
 */

import type { Personality } from "../chat-types";

export interface AgentChatBubbleProps {
  role: "user" | "assistant";
  text: string;
  /** Personality for assistant messages (avatar, brand color). */
  personality?: Personality;
  /** Override class on the outer wrapper. */
  className?: string;
}

export function AgentChatBubble({ role, text, personality, className }: AgentChatBubbleProps) {
  const isUser = role === "user";
  const brandColor = personality?.brand?.primaryColor;
  const avatar = personality?.assets?.avatarSmall ?? personality?.assets?.avatarLight;

  return (
    <div
      className={`nexo-chat-bubble nexo-chat-bubble--${role} ${className ?? ""}`}
      style={!isUser && brandColor ? { "--nexo-bubble-accent": brandColor } as React.CSSProperties : undefined}
    >
      {!isUser && avatar && (
        <img
          className="nexo-chat-bubble__avatar"
          src={avatar}
          alt={personality?.name ?? ""}
          width={28}
          height={28}
        />
      )}
      <div className="nexo-chat-bubble__content">
        {text || <span className="nexo-chat-bubble__typing" />}
      </div>
    </div>
  );
}
