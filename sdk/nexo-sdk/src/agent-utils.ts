export function buildAgentThreadStorageKey(
  storagePrefix: string,
  appId: string,
  userId: string,
): string {
  return `${storagePrefix}:${appId}:${userId}`;
}

export function buildAgentDeviceThreadStorageKey(
  storagePrefix: string,
  appId: string,
  deviceKey: string,
): string {
  return `${storagePrefix}:${appId}:device:${deviceKey}`;
}

export function clearAgentThreadStorage(options: {
  storagePrefix: string;
  appId: string;
  userId: string;
  deviceKey?: string | null;
}): void {
  localStorage.removeItem(
    buildAgentThreadStorageKey(options.storagePrefix, options.appId, options.userId),
  );
  if (options.deviceKey) {
    localStorage.removeItem(
      buildAgentDeviceThreadStorageKey(
        options.storagePrefix,
        options.appId,
        options.deviceKey,
      ),
    );
  }
}

export function clearAgentThreadStorageForApp(
  storagePrefix: string,
  appId: string,
): void {
  const prefix = `${storagePrefix}:${appId}:`;
  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const key = localStorage.key(i);
    if (key && key.startsWith(prefix)) {
      keysToRemove.push(key);
    }
  }
  for (const key of keysToRemove) {
    localStorage.removeItem(key);
  }
}

export function migrateAgentThreadStorage(options: {
  storagePrefix: string;
  appId: string;
  userId: string;
  deviceKey?: string | null;
}): string | null {
  const userKey = buildAgentThreadStorageKey(
    options.storagePrefix,
    options.appId,
    options.userId,
  );
  const existing = localStorage.getItem(userKey);
  if (existing) {
    return existing;
  }
  if (!options.deviceKey) {
    return null;
  }

  const deviceKey = buildAgentDeviceThreadStorageKey(
    options.storagePrefix,
    options.appId,
    options.deviceKey,
  );
  const deviceThread = localStorage.getItem(deviceKey);
  if (!deviceThread) {
    return null;
  }

  localStorage.setItem(userKey, deviceThread);
  return deviceThread;
}

function parsePromptSuggestions(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

export function extractPromptSuggestionsFromAgentCard(
  card: unknown,
  capabilityName?: string | null,
): string[] {
  if (!card || typeof card !== "object") {
    return [];
  }
  const c = card as Record<string, unknown>;

  // Format 0: Nexo per-app agent card - top-level skills[].luzia.example_invocations
  const skills = c.skills;
  if (Array.isArray(skills) && skills.length > 0) {
    const preferredSkill =
      (capabilityName
        ? skills.find((item) => {
            if (!item || typeof item !== "object") return false;
            const record = item as Record<string, unknown>;
            return record.id === capabilityName || record.name === capabilityName;
          })
        : null) ?? skills[0];

    if (preferredSkill && typeof preferredSkill === "object") {
      const luzia = (preferredSkill as Record<string, unknown>).luzia;
      if (luzia && typeof luzia === "object") {
        const fromSkillExamples = parsePromptSuggestions(
          (luzia as Record<string, unknown>).example_invocations,
        );
        if (fromSkillExamples.length > 0) return fromSkillExamples;
      }
    }
  }

  // Format 1: A2A capabilities.items[].metadata.prompt_suggestions
  const capabilities = c.capabilities;
  if (capabilities && typeof capabilities === "object") {
    const items = (capabilities as Record<string, unknown>).items;
    if (Array.isArray(items) && items.length > 0) {
      const preferredItem =
        (capabilityName
          ? items.find((item) => {
              if (!item || typeof item !== "object") return false;
              return (item as Record<string, unknown>).name === capabilityName;
            })
          : null) ?? items[0];

      if (preferredItem && typeof preferredItem === "object") {
        const metadata = (preferredItem as Record<string, unknown>).metadata;
        if (metadata && typeof metadata === "object") {
          const fromMeta = parsePromptSuggestions(
            (metadata as Record<string, unknown>).prompt_suggestions,
          );
          if (fromMeta.length > 0) return fromMeta;
        }
      }
    }
  }

  // Format 2: Nexo agent card - luzia.example_invocations
  const luzia = c.luzia;
  if (luzia && typeof luzia === "object") {
    const examples = (luzia as Record<string, unknown>).example_invocations;
    const fromExamples = parsePromptSuggestions(examples);
    if (fromExamples.length > 0) return fromExamples;
  }

  return [];
}

export async function loadAgentPromptSuggestions(
  agentCardUrl: string,
  options: {
    capabilityName?: string | null;
    fetchImpl?: typeof fetch;
  } = {},
): Promise<string[]> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const response = await fetchImpl(agentCardUrl);
  if (!response.ok) {
    return [];
  }

  return extractPromptSuggestionsFromAgentCard(
    await response.json(),
    options.capabilityName,
  );
}
