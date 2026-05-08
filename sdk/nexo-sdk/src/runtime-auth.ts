import type { NexoRuntimeAuthMode } from "./types";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"]);
const FIRST_PARTY_HOSTS = new Set([
  "apps.staging.luzia.com",
  "apps.luzia.com",
]);

function normalizeHost(host: string | null | undefined): string {
  return host?.split(":")[0]?.trim().toLowerCase() ?? "";
}

export function isFirstPartyHostedAppHost(
  host: string | null | undefined,
): boolean {
  const hostname = normalizeHost(host);
  return LOCAL_HOSTS.has(hostname) || FIRST_PARTY_HOSTS.has(hostname);
}

export function resolveRuntimeApiBaseUrl(options: {
  apiBaseUrl: string;
  authBaseUrl: string | null | undefined;
  appHost: string | null | undefined;
}): {
  apiBaseUrl: string;
  hostedSessionApiBaseUrl: string | null;
  hostedSessionCapable: boolean;
} {
  const hostedSessionApiBaseUrl =
    options.authBaseUrl && isFirstPartyHostedAppHost(options.appHost)
      ? new URL("/app-runtime-api", options.authBaseUrl).toString()
      : null;

  return {
    // Keep the direct API origin as the canonical bearer/domain-session path.
    // Hosted session bootstrap is an optional auth-host overlay, not a
    // wholesale replacement for standalone runtime traffic.
    apiBaseUrl: options.apiBaseUrl,
    hostedSessionApiBaseUrl,
    hostedSessionCapable: hostedSessionApiBaseUrl !== null,
  };
}

export function buildNexoRequestInit(options: {
  accessToken?: string | null;
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  cache?: RequestCache;
  signal?: AbortSignal;
}): RequestInit {
  const headers = new Headers(options.headers);
  if (options.accessToken) {
    headers.set("Authorization", `Bearer ${options.accessToken}`);
  }
  const hasHeaders = Array.from(headers.keys()).length > 0;

  const init: RequestInit = {
    ...(options.method ? { method: options.method } : {}),
    ...(hasHeaders ? { headers } : {}),
    ...(typeof options.cache === "string" ? { cache: options.cache } : {}),
    ...(options.body !== undefined ? { body: options.body } : {}),
    ...(options.signal ? { signal: options.signal } : {}),
  };

  if (!options.accessToken) {
    init.credentials = "include";
  }

  return init;
}

export function resolveRuntimeAuthMode(
  accessToken: string | null | undefined,
): NexoRuntimeAuthMode {
  return accessToken ? "bearer" : "hosted_session";
}
