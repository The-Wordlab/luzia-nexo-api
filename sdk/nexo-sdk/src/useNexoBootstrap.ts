/**
 * Listen for nexo:bootstrap postMessage from the Nexo launch page.
 *
 * Validates that the message comes from a trusted Nexo origin by checking
 * against the api_base_url origins in nexo.json.
 */

import { useEffect, useState } from "react";
import type { NexoBootstrap } from "./types";
import { extractTrustedOriginsFromSiteConfig, loadNexoSiteConfig } from "./site-config";

/** Known Nexo origins that can send bootstrap messages. */
const TRUSTED_NEXO_ORIGINS = new Set([
  "http://localhost:3000",
  "http://localhost:8000",
]);

/** Load additional trusted origins from nexo.json. */
async function loadTrustedOrigins(): Promise<Set<string>> {
  const origins = new Set(TRUSTED_NEXO_ORIGINS);
  const siteConfig = await loadNexoSiteConfig();
  for (const origin of extractTrustedOriginsFromSiteConfig(siteConfig)) {
    origins.add(origin);
  }
  return origins;
}

export function useNexoBootstrap(): NexoBootstrap | null {
  const [bootstrap, setBootstrap] = useState<NexoBootstrap | null>(null);

  useEffect(() => {
    let trustedOrigins: Set<string> = TRUSTED_NEXO_ORIGINS;

    // Load additional origins from public site config
    loadTrustedOrigins().then((origins) => {
      trustedOrigins = origins;
    });

    function handler(event: MessageEvent) {
      if (event.data?.type !== "nexo:bootstrap") return;

      // Validate sender origin
      if (!trustedOrigins.has(event.origin)) {
        console.warn(
          `[nexo-bootstrap] Rejected message from untrusted origin: ${event.origin}`,
        );
        return;
      }

      setBootstrap(event.data as NexoBootstrap);
    }

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  return bootstrap;
}
