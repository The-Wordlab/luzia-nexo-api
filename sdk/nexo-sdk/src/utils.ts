/**
 * Shared utility functions for Nexo apps.
 */

/** Read a query parameter from the current URL. */
export function getQueryParam(name: string): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get(name);
}

/**
 * Unwrap a potentially paginated API response.
 *
 * The Nexo structured app query endpoint returns `{ items: [...], total, limit, offset }`
 * for paginated responses or a plain array for legacy/non-paginated responses.
 * This helper normalizes both shapes to a plain array.
 */
export function unwrapRecords<T>(data: T[] | { items: T[]; total: number }): T[] {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && "items" in data) {
    return (data as { items: T[] }).items;
  }
  return [];
}

/**
 * Resolve a demo persona ID from the `?persona=` query parameter.
 *
 * Returns null if no persona param is present or the value is not in the
 * provided list of valid persona IDs.
 */
export function resolveDemoPersonaId(validIds?: string[]): string | null {
  const id = getQueryParam("persona");
  if (!id) return null;
  if (validIds && !validIds.includes(id)) return null;
  return id;
}
