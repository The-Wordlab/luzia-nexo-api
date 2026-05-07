import { describe, it, expect, beforeEach } from "vitest";
import {
  registerBlockRenderer,
  getBlockRenderer,
  clearBlockRenderers,
} from "./content-blocks";
import type { ContentBlock } from "./chat-types";

describe("content-blocks registry", () => {
  beforeEach(() => {
    clearBlockRenderers();
  });

  it("returns undefined for unregistered format", () => {
    expect(getBlockRenderer("unknown.format")).toBeUndefined();
  });

  it("registers and retrieves a renderer", () => {
    const renderer = (block: ContentBlock) => {
      void block;
      return null;
    };
    registerBlockRenderer("nutrition.daily_summary", renderer);
    expect(getBlockRenderer("nutrition.daily_summary")).toBe(renderer);
  });

  it("overwrites a previously registered renderer", () => {
    const first = (block: ContentBlock) => {
      void block;
      return null;
    };
    const second = (block: ContentBlock) => {
      void block;
      return null;
    };
    registerBlockRenderer("test.format", first);
    registerBlockRenderer("test.format", second);
    expect(getBlockRenderer("test.format")).toBe(second);
  });

  it("clearBlockRenderers removes all registrations", () => {
    registerBlockRenderer("a.format", () => null);
    registerBlockRenderer("b.format", () => null);
    clearBlockRenderers();
    expect(getBlockRenderer("a.format")).toBeUndefined();
    expect(getBlockRenderer("b.format")).toBeUndefined();
  });

  it("different formats are independent", () => {
    const rendererA = (block: ContentBlock) => {
      void block;
      return null;
    };
    const rendererB = (block: ContentBlock) => {
      void block;
      return null;
    };
    registerBlockRenderer("format.a", rendererA);
    registerBlockRenderer("format.b", rendererB);
    expect(getBlockRenderer("format.a")).toBe(rendererA);
    expect(getBlockRenderer("format.b")).toBe(rendererB);
  });
});
