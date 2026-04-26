import { NEXO_API_URL, NEXO_APP_ID, NEXO_WEBHOOK_SECRET } from "./config";
import { signRequest } from "./lib/signing";

export interface LinkStartResult {
  link_session_id: string;
  link_status: "new" | "linked" | "confirm_required";
  nexo_user_id?: string;
  access_token?: string;
  token_expires_in?: number;
  existing_user_hint?: string;
}

export interface LinkConfirmResult {
  link_status: string;
  nexo_user_id: string;
  access_token: string;
  token_expires_in: number;
}

export interface TokenRefreshResult {
  nexo_user_id: string;
  access_token: string;
  token_expires_in: number;
}

export interface LinkStatusResult {
  linked: boolean;
  nexo_user_id?: string;
  phone_e164?: string;
  linked_at?: string;
}

export class NexoIdentityBridgeClient {
  private apiUrl: string;
  private appId: string;
  private secret: string;

  constructor(
    apiUrl = NEXO_API_URL,
    appId = NEXO_APP_ID,
    secret = NEXO_WEBHOOK_SECRET,
  ) {
    this.apiUrl = apiUrl;
    this.appId = appId;
    this.secret = secret;
  }

  async linkStart(
    phone_e164: string,
    external_user_id: string,
    metadata?: Record<string, string>,
  ): Promise<LinkStartResult> {
    return this.signedPost("/api/identity-bridge/link-start", {
      phone_e164,
      external_user_id,
      metadata: metadata || {},
    });
  }

  async linkConfirm(link_session_id: string): Promise<LinkConfirmResult> {
    return this.signedPost("/api/identity-bridge/link-confirm", {
      link_session_id,
      confirmed: true,
    });
  }

  async tokenRefresh(external_user_id: string): Promise<TokenRefreshResult> {
    return this.signedPost("/api/identity-bridge/token-refresh", {
      external_user_id,
    });
  }

  async linkStatus(external_user_id: string): Promise<LinkStatusResult> {
    return this.signedGet(
      `/api/identity-bridge/link-status?external_user_id=${encodeURIComponent(external_user_id)}`,
    );
  }

  private async signedPost<T>(path: string, body: unknown): Promise<T> {
    const rawBody = JSON.stringify(body);
    const { timestamp, signature } = signRequest(this.secret, rawBody);

    const resp = await fetch(`${this.apiUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-App-Id": this.appId,
        "X-App-Secret": this.secret,
        "X-Timestamp": String(timestamp),
        "X-Signature": signature,
      },
      body: rawBody,
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`Nexo API ${resp.status}: ${text}`);
    }

    return (await resp.json()) as T;
  }

  private async signedGet<T>(path: string): Promise<T> {
    const rawBody = "";
    const { timestamp, signature } = signRequest(this.secret, rawBody);

    const resp = await fetch(`${this.apiUrl}${path}`, {
      method: "GET",
      headers: {
        "X-App-Id": this.appId,
        "X-App-Secret": this.secret,
        "X-Timestamp": String(timestamp),
        "X-Signature": signature,
      },
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`Nexo API ${resp.status}: ${text}`);
    }

    return (await resp.json()) as T;
  }
}
