/**
 * Full chat panel - message list, input, optional personality selector.
 *
 * Designed to be mounted inside a dialog/bottom-sheet or inline.
 * Controlled - the host provides messages, personality, and callbacks.
 */

import { useEffect, useRef, useState } from "react";
import type { ChatMessage, Personality } from "../chat-types";
import { AgentChatBubble } from "./AgentChatBubble";
import { AgentSuggestionChips } from "./AgentSuggestionChips";

export interface AgentChatPanelProps {
  messages: ChatMessage[];
  suggestions: string[];
  sending: boolean;
  progress: string | null;
  error: string | null;
  onSendMessage: (text: string) => void;
  onClearThread: () => void;
  /** Active personality (shown on assistant bubbles). */
  personality?: Personality;
  /** Placeholder text for the input. Required - host provides translation. */
  placeholder: string;
  /** Label for the clear/new-chat button. Required - host provides translation. */
  clearLabel: string;
  /** Label for the close button. Required - host provides translation. */
  closeLabel: string;
  /** Called when the user taps close. */
  onClose?: () => void;
  /** Title shown in the header. */
  title?: string;
  /** Empty-state welcome title shown before the first user turn. */
  welcomeTitle?: string;
  /** Optional empty-state supporting copy. */
  welcomeDescription?: string;
  className?: string;
}

export function AgentChatPanel(props: AgentChatPanelProps) {
  const {
    messages,
    suggestions,
    sending,
    progress,
    error,
    onSendMessage,
    personality,
    placeholder,
    closeLabel,
    onClose,
    className,
    title,
    welcomeTitle,
    welcomeDescription,
  } = props;
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const visibleMessages = messages.filter((message) => message.text.trim().length > 0);
  const latestAssistantMessage = [...messages]
    .reverse()
    .find((message) => message.role === "assistant");
  const isEmpty = visibleMessages.length === 0;
  const showStarterSuggestions = !sending && isEmpty;
  const showFollowUpSuggestions =
    !sending &&
    !isEmpty &&
    suggestions.length > 0 &&
    latestAssistantMessage !== undefined;
  const showTypingIndicator =
    sending &&
    (!latestAssistantMessage || latestAssistantMessage.text.trim().length === 0);
  const resolvedTitle = title ?? personality?.name ?? placeholder;
  const resolvedWelcomeTitle =
    welcomeTitle ?? personality?.greeting ?? resolvedTitle;

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    if (typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [messages, progress, sending]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || sending) return;
    onSendMessage(input.trim());
    setInput("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    if (!input.trim() || sending) return;
    onSendMessage(input.trim());
    setInput("");
  }

  function handleSuggestion(text: string) {
    onSendMessage(text);
  }

  return (
    <div className={`nexo-chat-panel ${className ?? ""}`}>
      <div className="nexo-chat-panel__header">
        <div className="nexo-chat-panel__header-title">
          <svg className="nexo-chat-panel__header-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <span>{resolvedTitle}</span>
        </div>
        <div className="nexo-chat-panel__header-actions">
          {messages.length > 0 && (
            <button
              type="button"
              className="nexo-chat-panel__icon-button"
              onClick={props.onClearThread}
              aria-label={props.clearLabel}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
            </button>
          )}
          {onClose && (
            <button
              type="button"
              className="nexo-chat-panel__icon-button nexo-chat-panel__icon-button--close"
              onClick={onClose}
              aria-label={closeLabel}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className="nexo-chat-panel__messages" ref={scrollRef}>
        {showStarterSuggestions && (
          <div className="nexo-chat-panel__empty-state">
            <div className="nexo-chat-panel__empty-icon" aria-hidden="true">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div className="nexo-chat-panel__empty-copy">
              <p className="nexo-chat-panel__empty-title">{resolvedWelcomeTitle}</p>
              {welcomeDescription ? (
                <p className="nexo-chat-panel__empty-description">
                  {welcomeDescription}
                </p>
              ) : null}
            </div>
            {suggestions.length > 0 ? (
              <AgentSuggestionChips
                suggestions={suggestions}
                onSelect={handleSuggestion}
              />
            ) : null}
          </div>
        )}
        {visibleMessages.map((msg) => (
          <AgentChatBubble
            key={msg.id}
            role={msg.role}
            text={msg.text}
            personality={msg.role === "assistant" ? personality : undefined}
          />
        ))}
        {showTypingIndicator && (
          <div className="nexo-chat-panel__thinking">
            <svg className="nexo-chat-panel__spinner" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            <span>{progress ?? ""}</span>
          </div>
        )}
        {showFollowUpSuggestions && (
          <AgentSuggestionChips
            suggestions={suggestions}
            onSelect={handleSuggestion}
            className="nexo-chat-panel__follow-ups"
          />
        )}
        {error && isEmpty && !showTypingIndicator ? (
          <div className="nexo-chat-panel__error">{error}</div>
        ) : null}
      </div>

      <form className="nexo-chat-panel__input-bar" onSubmit={handleSubmit}>
        <div className="nexo-chat-panel__input-shell">
          <input
            ref={inputRef}
            className="nexo-chat-panel__input"
            type="text"
            value={input}
            placeholder={placeholder}
            autoComplete="off"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending}
          />
          <button
            type="submit"
            className="nexo-chat-panel__send"
            disabled={sending || !input.trim()}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13" />
              <path d="M22 2L15 22L11 13L2 9L22 2Z" />
            </svg>
          </button>
        </div>
      </form>
    </div>
  );
}
