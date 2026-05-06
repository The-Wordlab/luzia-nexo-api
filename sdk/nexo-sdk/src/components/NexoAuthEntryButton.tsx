/**
 * "Sign in with Luzia" button.
 *
 * Used by hosted webview apps to initiate the auth bridge flow.
 * Controlled - the host provides the click handler and size.
 * Theming uses CSS variables so each app can adapt it.
 */

export interface NexoAuthEntryButtonProps {
  onClick: () => void;
  size?: "hero" | "compact";
  /** Label text. Required - host provides translation. */
  label: string;
  /** Avatar image URL. */
  avatarSrc?: string;
  pending?: boolean;
  className?: string;
}

/**
 * Default avatar path - relative so it works with any Vite base URL.
 * Each app must place luzia-avatar.svg in public/luzia/avatars/.
 * A canonical copy lives in apps/nexo-sdk/assets/luzia/avatars/.
 */
const DEFAULT_AVATAR = "./luzia/avatars/luzia-avatar.svg";

export function NexoAuthEntryButton({
  onClick,
  size = "hero",
  label,
  avatarSrc = DEFAULT_AVATAR,
  pending = false,
  className,
}: NexoAuthEntryButtonProps) {
  const isCompact = size === "compact";

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="nexo-auth-entry-button"
      disabled={pending}
      aria-busy={pending ? "true" : undefined}
      className={`nexo-auth-entry-button ${isCompact ? "nexo-auth-entry-button--compact" : ""} ${
        pending ? "nexo-auth-entry-button--pending" : ""
      } ${className ?? ""}`}
    >
      <span className="nexo-auth-entry-button__avatar">
        <img
          src={avatarSrc}
          alt=""
          aria-hidden="true"
          className="nexo-auth-entry-button__avatar-img"
        />
      </span>
      {pending ? (
        <span
          className="nexo-auth-entry-button__spinner"
          aria-hidden="true"
        />
      ) : null}
      <span className="nexo-auth-entry-button__label">{label}</span>
    </button>
  );
}
