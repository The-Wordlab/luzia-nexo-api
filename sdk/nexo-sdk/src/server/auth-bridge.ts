/**
 * Nexo auth bridge for hosted webview apps.
 *
 * Handles the short-code exchange flow:
 * 1. POST /auth/nexo/prepare - stores guest token in httpOnly cookie
 * 2. GET /auth/nexo/callback - exchanges code for session, redirects
 * 3. GET /auth/nexo/session - returns session to client, clears cookie
 *
 * The developer provides config (API URL, app ID, secret) and gets
 * a working auth flow with guest continuity. No auth implementation needed.
 */

import type { Router, Request, Response } from "express";
import { signRequest } from "./signature";

export interface NexoAuthBridgeConfig {
  /** Nexo backend API URL. */
  nexoApiUrl: string;
  /** The Connected App ID that owns the auth handoff. */
  connectedAppId: string;
  /** The Connected App's webhook secret (X-App-Secret). */
  appSecret: string;
  /** Cookie name prefix (default: "nexo_auth"). */
  cookiePrefix?: string;
}

interface SessionCookiePayload {
  accessToken: string;
  userId: string;
  appId: string;
  accessState: string;
}

interface GuestBridgeCookiePayload {
  guestToken: string;
}

const GUEST_BRIDGE_TTL_MS = 15 * 60 * 1000;

function isSecureRequest(request: Request): boolean {
  const proto = request.header("x-forwarded-proto");
  if (typeof proto === "string") return proto.split(",")[0]?.trim() === "https";
  return request.protocol === "https";
}

function parseCookieHeader(request: Request): Record<string, string> {
  const raw = request.header("cookie");
  if (!raw) return {};
  return raw.split(";").reduce<Record<string, string>>((acc, chunk) => {
    const sep = chunk.indexOf("=");
    if (sep <= 0) return acc;
    const key = chunk.slice(0, sep).trim();
    const value = chunk.slice(sep + 1).trim();
    if (key) acc[key] = decodeURIComponent(value);
    return acc;
  }, {});
}

function serialize(payload: object): string {
  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

function parseSession(raw: string | undefined): SessionCookiePayload | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as Partial<SessionCookiePayload>;
    if (!parsed.accessToken || !parsed.userId || !parsed.appId || !parsed.accessState) return null;
    return parsed as SessionCookiePayload;
  } catch {
    return null;
  }
}

function parseGuestToken(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as Partial<GuestBridgeCookiePayload>;
    return parsed.guestToken || null;
  } catch {
    return null;
  }
}

function normalizeNext(raw: string | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}

function appendError(path: string, errorKey: string): string {
  const url = new URL(path, "http://localhost");
  url.searchParams.set("auth_error", errorKey);
  return `${url.pathname}${url.search}`;
}

/**
 * Create an Express router that handles the Nexo auth bridge flow.
 *
 * Mount at your app root:
 *   app.use(createNexoAuthRouter(config));
 *
 * This gives you:
 *   POST /auth/nexo/prepare   - store guest token
 *   GET  /auth/nexo/callback  - exchange code, set session cookie
 *   GET  /auth/nexo/session   - return session to client
 */
export function createNexoAuthRouter(config: NexoAuthBridgeConfig): Router {
  // Dynamic import to avoid requiring express as a dependency
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { Router: ExpressRouter } = require("express") as typeof import("express");
  const router = ExpressRouter();

  const prefix = config.cookiePrefix ?? "nexo_auth";
  const sessionCookie = `${prefix}_auth_bridge`;
  const guestCookie = `${prefix}_guest_bridge`;

  const cookieOpts = (req: Request) => ({
    httpOnly: true,
    sameSite: "lax" as const,
    secure: isSecureRequest(req),
    path: "/",
  });

  function clearGuest(req: Request, res: Response) {
    res.clearCookie(guestCookie, cookieOpts(req));
  }

  // 1. Prepare: store guest token for continuity across auth flow
  router.post("/auth/nexo/prepare", (req: Request, res: Response) => {
    const guestToken = typeof req.body?.guest_token === "string" ? req.body.guest_token.trim() : "";
    if (!guestToken) {
      clearGuest(req, res);
      res.status(400).json({ error: "ERROR_AUTH_BRIDGE_NO_GUEST_TOKEN" });
      return;
    }
    res.cookie(guestCookie, serialize({ guestToken }), {
      ...cookieOpts(req),
      maxAge: GUEST_BRIDGE_TTL_MS,
    });
    res.status(204).end();
  });

  // 2. Callback: exchange code for session
  router.get("/auth/nexo/callback", async (req: Request, res: Response) => {
    const code = typeof req.query.code === "string" ? req.query.code : undefined;
    const appId = typeof req.query.app_id === "string" ? req.query.app_id : undefined;
    const deviceKey = typeof req.query.device_key === "string" ? req.query.device_key : undefined;
    const nextPath = normalizeNext(typeof req.query.next === "string" ? req.query.next : undefined);
    const guestToken = parseGuestToken(parseCookieHeader(req)[guestCookie]);

    if (!code || !appId || !deviceKey) {
      clearGuest(req, res);
      res.redirect(302, appendError(nextPath, "ERROR_AUTH_BRIDGE_CALLBACK_INVALID"));
      return;
    }

    try {
      const exchangeBody = JSON.stringify({ launch_code: code, app_id: appId, device_key: deviceKey });
      const exchangeResp = await fetch(
        `${config.nexoApiUrl}/api/apps/structured/apps/${config.connectedAppId}/auth-handoffs/exchange`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...signRequest(config.connectedAppId, config.appSecret, exchangeBody),
          },
          body: exchangeBody,
        },
      );

      if (!exchangeResp.ok) {
        clearGuest(req, res);
        res.redirect(302, appendError(nextPath, "ERROR_AUTH_BRIDGE_EXCHANGE_FAILED"));
        return;
      }

      const payload = (await exchangeResp.json()) as Record<string, unknown>;
      if (!payload.access_token || !payload.user_id || !payload.app_id || !payload.access_state) {
        clearGuest(req, res);
        res.redirect(302, appendError(nextPath, "ERROR_AUTH_BRIDGE_EXCHANGE_FAILED"));
        return;
      }

      // Best-effort guest migration
      if (guestToken) {
        try {
          await fetch(`${config.nexoApiUrl}/api/auth/migrate-guest`, {
            method: "POST",
            headers: { Authorization: `Bearer ${payload.access_token}`, "Content-Type": "application/json" },
            body: JSON.stringify({ guest_token: guestToken }),
          });
        } catch { /* continuity is best effort */ }
      }

      res.cookie(sessionCookie, serialize({
        accessToken: payload.access_token,
        userId: payload.user_id,
        appId: payload.app_id,
        accessState: payload.access_state,
      }), {
        ...cookieOpts(req),
        maxAge: typeof payload.expires_in_seconds === "number" ? payload.expires_in_seconds * 1000 : undefined,
      });
      clearGuest(req, res);
      res.redirect(302, nextPath);
    } catch {
      clearGuest(req, res);
      res.redirect(302, appendError(nextPath, "ERROR_AUTH_BRIDGE_EXCHANGE_FAILED"));
    }
  });

  // 3. Session: return credentials to client, clear cookie
  router.get("/auth/nexo/session", (req: Request, res: Response) => {
    const session = parseSession(parseCookieHeader(req)[sessionCookie]);
    if (!session) {
      res.status(204).end();
      return;
    }
    res.clearCookie(sessionCookie, cookieOpts(req));
    res.json({
      access_token: session.accessToken,
      user_id: session.userId,
      app_id: session.appId,
      access_state: session.accessState,
    });
  });

  return router;
}
