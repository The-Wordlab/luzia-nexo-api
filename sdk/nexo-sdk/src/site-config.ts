/**
 * Load and resolve nexo.json site configuration.
 *
 * nexo.json is the public config file served alongside the app. The SDK knows
 * the standard Nexo stage/prod hosts already, so apps only need nexo.json for
 * their slug plus any explicit local/custom-host overrides.
 */

import type { NexoSiteConfig, NexoSiteEnvironmentConfig } from "./types";

type KnownEnvironmentName = "local" | "staging" | "production";

const KNOWN_ENVIRONMENT_CONFIG: Record<KnownEnvironmentName, NexoSiteEnvironmentConfig> = {
  local: {
    api_base_url: "http://localhost:8000",
    auth_base_url: "http://localhost:3000",
  },
  staging: {
    api_base_url: "https://nexo-cdn-alb.staging.thewordlab.net",
    auth_base_url: "https://staging.nexo.luzia.com",
  },
  production: {
    api_base_url: "https://luzia-nexo.thewordlab.net",
    auth_base_url: "https://nexo.luzia.com",
  },
};

function normalizeEnvironmentName(envHint: string | null): KnownEnvironmentName | null {
  switch ((envHint || "").toLowerCase()) {
    case "local":
    case "localhost":
    case "development":
    case "dev":
      return "local";
    case "staging":
    case "stage":
      return "staging";
    case "production":
    case "prod":
      return "production";
    default:
      return null;
  }
}

function resolveKnownEnvironmentName(
  options: { host: string; envHint: string | null },
): KnownEnvironmentName | null {
  const hinted = normalizeEnvironmentName(options.envHint);
  if (hinted) return hinted;

  const host = options.host.toLowerCase();
  if (
    host === "localhost" ||
    host.startsWith("localhost:") ||
    host === "127.0.0.1" ||
    host.startsWith("127.0.0.1:")
  ) {
    return "local";
  }
  if (
    host === "apps.staging.luzia.com" ||
    host === "nexo-apps.staging.thewordlab.net" ||
    host === "staging.nexo.luzia.com"
  ) {
    return "staging";
  }
  if (
    host === "apps.luzia.com" ||
    host === "nexo-apps.thewordlab.net" ||
    host === "nexo.luzia.com"
  ) {
    return "production";
  }
  return null;
}

function resolveKnownEnvironmentConfig(
  options: { host: string; envHint: string | null },
): NexoSiteEnvironmentConfig | null {
  const environment = resolveKnownEnvironmentName(options);
  return environment ? KNOWN_ENVIRONMENT_CONFIG[environment] : null;
}

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
  const { host } = options;
  const environment = resolveKnownEnvironmentName(options);
  if (!config?.environments) {
    return resolveKnownEnvironmentConfig(options);
  }

  if (environment) {
    const envConfig = config.environments[environment];
    if (envConfig) return envConfig;
  }

  return config.environments[host] ?? resolveKnownEnvironmentConfig(options);
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
  const knownOrigins = Object.values(KNOWN_ENVIRONMENT_CONFIG)
    .map((env) => env.api_base_url)
    .filter((value): value is string => typeof value === "string");
  for (const originCandidate of knownOrigins) {
    try {
      origins.add(new URL(originCandidate).origin);
    } catch {
      // Ignore invalid URLs in SDK defaults.
    }
  }
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
