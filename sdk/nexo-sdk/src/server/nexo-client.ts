/**
 * NexoServerClient - typed Nexo API client for server-to-server use.
 *
 * Authenticates via developer key exchange and provides typed wrappers for
 * Knowledge Packs, External Sync, Apps, Table Records, Profiles, and
 * Demo Personas.
 *
 * Node-only. No browser APIs.
 */

export interface NexoServerClientConfig {
  /** Nexo API base URL (e.g. "http://localhost:8000") */
  apiUrl: string;
  /** Developer key for authentication */
  developerKey?: string;
  /** Pre-authenticated bearer token (skips key exchange) */
  bearerToken?: string;
}

export interface NexoNativeSessionExchangeInput {
  accessToken: string;
  deviceKey?: string | null;
  masterUserId?: string | null;
  adId?: string | null;
  organizationId?: string | null;
  apiKey?: string | null;
  correlationId?: string | null;
  countryCode?: string | null;
  acceptLanguage?: string | null;
  userTheme?: string | null;
  userAgent?: string | null;
}

export interface NexoNativeSessionExchangeResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  user_id: string;
  master_user_id: string;
}

function appendOptionalHeader(
  headers: Record<string, string>,
  key: string,
  value: string | null | undefined,
): void {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (normalized) {
    headers[key] = normalized;
  }
}

export class NexoRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "NexoRequestError";
  }
}

export class NexoServerClient {
  private readonly apiUrl: string;
  private readonly developerKey: string | undefined;
  private token: string | null;

  constructor(config: NexoServerClientConfig) {
    this.apiUrl = config.apiUrl;
    this.developerKey = config.developerKey;
    this.token = config.bearerToken ?? null;
  }

  async authenticate(developerKey?: string): Promise<void> {
    const key = developerKey ?? this.developerKey;
    if (!key) throw new Error("No developer key provided");

    const resp = await fetch(`${this.apiUrl}/api/auth/key-exchange`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    if (!resp.ok) {
      throw new Error(`Key exchange failed: ${resp.status} ${resp.statusText}`);
    }
    const data = (await resp.json()) as { access_token: string };
    this.token = data.access_token;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    if (!this.token) {
      await this.authenticate();
    }

    const resp = await fetch(`${this.apiUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new NexoRequestError(
        `Nexo API ${method} ${path}: ${resp.status} ${text}`,
        resp.status,
      );
    }

    if (resp.status === 204) return undefined as T;
    return (await resp.json()) as T;
  }

  private async requestWithBearer<T>(
    method: string,
    path: string,
    bearerToken: string,
    body?: unknown,
  ): Promise<T> {
    const resp = await fetch(`${this.apiUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${bearerToken}`,
        "Content-Type": "application/json",
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new NexoRequestError(
        `Nexo API ${method} ${path}: ${resp.status} ${text}`,
        resp.status,
      );
    }

    if (resp.status === 204) return undefined as T;
    return (await resp.json()) as T;
  }

  // ---- Knowledge Packs ----

  async listKnowledgePacks(appId: string): Promise<KnowledgePack[]> {
    return this.request("GET", `/api/knowledge-packs?owner_type=app&owner_id=${appId}`);
  }

  async listKnowledgePackDatasets(packId: string): Promise<KnowledgePackDataset[]> {
    return this.request("GET", `/api/knowledge-packs/${packId}/datasets`);
  }

  async upsertRecord(
    packId: string,
    datasetId: string,
    recordKey: string,
    dataJson: Record<string, unknown>,
    searchText?: string,
  ): Promise<unknown> {
    return this.request(
      "PUT",
      `/api/knowledge-packs/${packId}/datasets/${datasetId}/records`,
      {
        record_key: recordKey,
        data_json: dataJson,
        search_text: searchText,
      },
    );
  }

  async listRecords(
    packId: string,
    datasetId: string,
    limit = 200,
  ): Promise<KPRecord[]> {
    return this.request(
      "GET",
      `/api/knowledge-packs/${packId}/datasets/${datasetId}/records?limit=${limit}`,
    );
  }

  async bulkUpsertRecords(
    packId: string,
    datasetId: string,
    records: { record_key: string; data_json: Record<string, unknown> }[],
  ): Promise<{ created: number; updated: number; total: number }> {
    return this.request(
      "POST",
      `/api/knowledge-packs/${packId}/datasets/${datasetId}/records/bulk`,
      records,
    );
  }

  // ---- External Sync ----

  async syncCapability(
    runtimeKey: string,
    capabilityKey: string,
    name: string,
    description?: string,
  ): Promise<unknown> {
    return this.request("PUT", "/api/external-sync/capabilities", {
      runtime_key: runtimeKey,
      capability_key: capabilityKey,
      name,
      description,
    });
  }

  async syncContextSummary(
    runtimeKey: string,
    summaryType: string,
    summaryKey: string,
    contentText: string,
    title?: string,
  ): Promise<unknown> {
    return this.request("PUT", "/api/external-sync/context-summaries", {
      runtime_key: runtimeKey,
      summary_type: summaryType,
      summary_key: summaryKey,
      content_text: contentText,
      title,
    });
  }

  async syncConnectedAppCapabilities(appId: string): Promise<unknown> {
    return this.request("POST", `/api/apps/${appId}/capabilities/sync`);
  }

  async listDemoPersonas(): Promise<DemoPersona[]> {
    return this.request("GET", "/api/demo/personas");
  }

  // ---- Apps ----

  async listApps(): Promise<App[]> {
    return this.request("GET", "/api/apps/structured");
  }

  async listAppParticipants(appId: string): Promise<AppParticipant[]> {
    return this.request("GET", `/api/apps/structured/${appId}/participants`);
  }

  async listAppTables(appId: string): Promise<AppTable[]> {
    return this.request("GET", `/api/apps/structured/${appId}/tables`);
  }

  // ---- Profiles ----

  async getMyProfile(accessToken?: string): Promise<NexoProfile> {
    if (accessToken) {
      return this.requestWithBearer("GET", "/api/me/profile", accessToken);
    }
    return this.request("GET", "/api/me/profile");
  }

  async exchangeNativeSession(
    slug: string,
    input: NexoNativeSessionExchangeInput,
  ): Promise<NexoNativeSessionExchangeResponse> {
    const accessToken = input.accessToken.trim();
    if (!accessToken) {
      throw new Error("No access token provided");
    }

    const headers: Record<string, string> = {
      Authorization: `Bearer ${accessToken}`,
    };
    appendOptionalHeader(headers, "X-DEVICE-KEY", input.deviceKey);
    appendOptionalHeader(headers, "X-MASTER-USER-ID", input.masterUserId);
    appendOptionalHeader(headers, "X-AD-ID", input.adId);
    appendOptionalHeader(headers, "X-ORGANIZATION-ID", input.organizationId);
    appendOptionalHeader(headers, "X-API-KEY", input.apiKey);
    appendOptionalHeader(headers, "X-CORRELATION-ID", input.correlationId);
    appendOptionalHeader(headers, "X-COUNTRY-CODE", input.countryCode);
    appendOptionalHeader(headers, "Accept-Language", input.acceptLanguage);
    appendOptionalHeader(headers, "X-USER-THEME", input.userTheme);
    appendOptionalHeader(headers, "User-Agent", input.userAgent);

    const path = `/api/apps/${slug}/native-session`;
    const resp = await fetch(`${this.apiUrl}${path}`, {
      method: "POST",
      headers,
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new NexoRequestError(
        `Nexo API POST ${path}: ${resp.status} ${text}`,
        resp.status,
      );
    }

    return (await resp.json()) as NexoNativeSessionExchangeResponse;
  }

  // ---- Table Records ----

  async queryTableRecords<T extends TableRecord = TableRecord>(
    tableId: string,
    body: TableQueryBody,
  ): Promise<TableQueryResponse<T>> {
    return this.request("POST", `/api/apps/structured/tables/${tableId}/query`, body);
  }

  async getTableRecord<T extends TableRecord = TableRecord>(
    tableId: string,
    recordId: string,
  ): Promise<T> {
    return this.request("GET", `/api/apps/structured/tables/${tableId}/records/${recordId}`);
  }

  async createTableRecord<T extends TableRecord = TableRecord>(
    tableId: string,
    body: TableRecordCreateBody,
  ): Promise<T> {
    return this.request("POST", `/api/apps/structured/tables/${tableId}/records`, body);
  }

  async updateTableRecord<T extends TableRecord = TableRecord>(
    tableId: string,
    recordId: string,
    body: TableRecordUpdateBody,
  ): Promise<T> {
    return this.request("PATCH", `/api/apps/structured/tables/${tableId}/records/${recordId}`, body);
  }

  async deleteTableRecord(tableId: string, recordId: string): Promise<void> {
    await this.request("DELETE", `/api/apps/structured/tables/${tableId}/records/${recordId}`);
  }
}

// ---- Types ----

export interface KPRecord {
  id: string;
  record_key: string;
  data_json: Record<string, unknown>;
}

export interface KnowledgePack {
  id: string;
  title: string;
  owner_type: string;
  owner_id: string;
  key?: string | null;
}

export interface KnowledgePackDataset {
  id: string;
  key: string;
  title: string;
}

export interface App {
  id: string;
  name: string;
  template_key: string | null;
}

export interface AppParticipant {
  id: string;
  app_id: string;
  user_id: string;
  role: string;
  status: string;
  joined_at: string;
  display_name?: string | null;
}

export interface NexoProfile {
  id: string;
  user_id: string;
  name?: string | null;
  locale?: string | null;
  country?: string | null;
  avatar_url?: string | null;
  role?: string | null;
  username?: string | null;
  display_name?: string | null;
}

export interface DemoPersona {
  id: string;
  display_name: string;
  locale: string;
  country: string;
  avatar_emoji: string;
  bio: string;
  consent_scopes: string[];
}

export interface AppTable {
  id: string;
  key: string;
  name: string;
}

export interface TableQueryFilter {
  field: string;
  op:
    | "eq"
    | "neq"
    | "in"
    | "contains"
    | "gt"
    | "gte"
    | "lt"
    | "lte"
    | "is_empty"
    | "is_not_empty";
  value?: unknown;
}

export interface TableQueryBody {
  filters?: TableQueryFilter[];
  limit?: number;
  offset?: number;
}

export interface TableRecord {
  id: string;
  created_at: string;
  updated_at: string | null;
  version?: number;
  values_json?: Record<string, unknown>;
  data_json?: Record<string, unknown>;
}

export interface TableQueryResponse<T extends TableRecord = TableRecord> {
  items: T[];
  total: number;
  limit?: number;
  offset?: number;
}

export interface TableRecordCreateBody {
  values_json: Record<string, unknown>;
}

export interface TableRecordUpdateBody {
  values_json: Record<string, unknown>;
  version: number;
}
