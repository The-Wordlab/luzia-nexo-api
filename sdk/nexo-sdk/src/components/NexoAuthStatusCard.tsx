/**
 * Auth bridge status card.
 *
 * Shows the appropriate UI based on auth state:
 * - Guest mode: "Sign in with Luzia" button
 * - Access pending: waiting card
 * - Invite required: invite card
 *
 * Controlled - the host provides auth state, labels, and handlers.
 */

import type { NexoAuthMode, NexoAccessState } from "../types";
import { NexoAuthEntryButton } from "./NexoAuthEntryButton";

/** Labels for access state cards. Host must provide translations. */
export interface NexoAuthStatusLabels {
  accessPendingTitle: string;
  accessPendingDesc: string;
  inviteRequiredTitle: string;
  inviteRequiredDesc: string;
  inviteCodeRequiredTitle: string;
  inviteCodeRequiredDesc: string;
  signInLabel: string;
}

export interface NexoAuthStatusCardProps {
  authMode: NexoAuthMode;
  accessState: NexoAccessState | null;
  onStartLogin: (() => void) | null;
  loginPending?: boolean;
  variant?: "hero" | "compact";
  /** Labels for access states. Required - host provides translations. */
  labels: NexoAuthStatusLabels;
  className?: string;
}

interface CardCopy {
  title: string;
  description: string;
}

function resolveCardCopy(
  accessState: NexoAccessState | null,
  labels: NexoAuthStatusLabels,
): CardCopy | null {
  switch (accessState) {
    case "access_pending":
      return { title: labels.accessPendingTitle, description: labels.accessPendingDesc };
    case "invite_code_required":
      return { title: labels.inviteCodeRequiredTitle, description: labels.inviteCodeRequiredDesc };
    case "invite_required":
      return { title: labels.inviteRequiredTitle, description: labels.inviteRequiredDesc };
    default:
      return null;
  }
}

export function NexoAuthStatusCard({
  authMode,
  accessState,
  onStartLogin,
  loginPending = false,
  variant = "hero",
  labels,
  className,
}: NexoAuthStatusCardProps) {
  // Guest mode with login available: show sign-in button
  if (authMode === "guest" && onStartLogin) {
    return (
      <section className={`nexo-auth-status-card ${className ?? ""}`} data-variant={variant}>
        <NexoAuthEntryButton
          onClick={onStartLogin}
          size={variant}
          label={labels.signInLabel}
          pending={loginPending}
        />
      </section>
    );
  }

  // Access state card
  const copy = resolveCardCopy(accessState, labels);
  if (!copy) return null;

  return (
    <section
      className={`nexo-auth-status-card nexo-auth-status-card--state ${className ?? ""}`}
      data-variant={variant}
    >
      <div className="nexo-auth-status-card__content">
        <p className="nexo-auth-status-card__title">{copy.title}</p>
        <p className="nexo-auth-status-card__desc">{copy.description}</p>
      </div>
    </section>
  );
}
