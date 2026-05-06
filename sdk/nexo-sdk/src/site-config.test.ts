import { describe, expect, it } from "vitest";
import {
  extractTrustedOriginsFromSiteConfig,
  resolveApiBaseUrlFromSiteConfig,
  resolveAuthBaseUrlFromSiteConfig,
} from "./site-config";

describe("site-config", () => {
  it("uses well-known production hosts when nexo.json only provides a slug", () => {
    const config = { slug: "nutrition" };
    const options = { host: "apps.luzia.com", envHint: null };

    expect(resolveApiBaseUrlFromSiteConfig(config, options)).toBe(
      "https://luzia-nexo.thewordlab.net",
    );
    expect(resolveAuthBaseUrlFromSiteConfig(config, options)).toBe(
      "https://nexo.luzia.com",
    );
  });

  it("uses well-known staging hosts for env hints on custom domains", () => {
    const config = { slug: "nutrition" };
    const options = { host: "preview.example.com", envHint: "staging" };

    expect(resolveApiBaseUrlFromSiteConfig(config, options)).toBe(
      "https://nexo-cdn-alb.staging.thewordlab.net",
    );
    expect(resolveAuthBaseUrlFromSiteConfig(config, options)).toBe(
      "https://staging.nexo.luzia.com",
    );
  });

  it("prefers explicit host overrides from nexo.json", () => {
    const config = {
      slug: "nutrition",
      environments: {
        "apps.luzia.com": {
          api_base_url: "https://custom-api.example.com",
          auth_base_url: "https://custom-auth.example.com",
        },
      },
    };
    const options = { host: "apps.luzia.com", envHint: null };

    expect(resolveApiBaseUrlFromSiteConfig(config, options)).toBe(
      "https://custom-api.example.com",
    );
    expect(resolveAuthBaseUrlFromSiteConfig(config, options)).toBe(
      "https://custom-auth.example.com",
    );
  });

  it("always trusts the standard Nexo API origins", () => {
    const origins = extractTrustedOriginsFromSiteConfig({ slug: "nutrition" });

    expect(origins.has("http://localhost:8000")).toBe(true);
    expect(origins.has("https://nexo-cdn-alb.staging.thewordlab.net")).toBe(true);
    expect(origins.has("https://luzia-nexo.thewordlab.net")).toBe(true);
  });
});
