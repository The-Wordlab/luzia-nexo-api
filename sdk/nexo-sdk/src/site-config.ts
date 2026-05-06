/**
 * Load and resolve nexo.json site configuration.
 *
 * nexo.json is the public config file served alongside the app. It maps
 * hostnames to Nexo API URLs so one build works across local dev, staging,
 * production, and CDN domains.
 */

import type { NexoSiteConfig, NexoSiteEnvironmentConfig } from "./types";

function getVersionHint(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("nexo_v");
}

export async function loadNexoSiteConfig(): Promise<NexoSiteConfig | null> {
  const versionHint = getVersionHint();
  try {
    // Use relative path so it resolves from the app's directory on CDN.
    // e.g. on https://apps.staging.luzia.com/nutrition/ this fetches
    // /nutrition/nexo.json, not /nexo.json at the CDN root.
    let path = "nexo.json";
    if (versionHint) {
      path += `?v=${encodeURIComponent(versionHint)}`;
    }
    const resp = await fetch(path, { cache: "no-store" });
    if (!resp.ok) return null;
    return (await resp.json()) as NexoSiteConfig;
  } catch {
    return null;
  }
}

function resolveEnvironmentConfig(
  config: NexoSiteConfig | null,
  options: { host: string; envHint: string | null },
): NexoSiteEnvironmentConfig | null {
  const { host, envHint } = options;
  if (!config?.environments) return null;

  if (envHint) {
    const envConfig = config.environments[envHint];
    if (envConfig) return envConfig;
  }

  return config.environments[host] ?? null;
}

export function resolveApiBaseUrlFromSiteConfig(
  config: NexoSiteConfig | null,
  options: { host: string; envHint: string | null },
): string | null {
  return resolveEnvironmentConfig(config, options)?.api_base_url ?? null;
}

export function resolveAuthBaseUrlFromSiteConfig(
  config: NexoSiteConfig | null,
  options: { host: string; envHint: string | null },
): string | null {
  return resolveEnvironmentConfig(config, options)?.auth_base_url ?? null;
}

export function resolveAppIdFromSiteConfig(
  config: NexoSiteConfig | null,
  options: { host: string; envHint: string | null },
): string | null {
  return resolveEnvironmentConfig(config, options)?.app_id ?? null;
}

export function extractTrustedOriginsFromSiteConfig(
  config: NexoSiteConfig | null,
): Set<string> {
  const origins = new Set<string>();
  if (!config?.environments) return origins;

  for (const env of Object.values(config.environments)) {
    if (!env?.api_base_url) continue;
    try {
      origins.add(new URL(env.api_base_url).origin);
    } catch {
      // Ignore invalid URLs in public config.
    }
  }

  return origins;
}
