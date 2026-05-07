import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentChatFab } from "./AgentChatFab";

describe("AgentChatFab", () => {
  const chatOptions = {
    apiBaseUrl: "https://luzia-nexo.thewordlab.net",
    appId: "app-1",
    userId: "user-1",
    accessToken: "token",
    slug: "nutrition",
    storagePrefix: "nutrition",
    capabilityName: "nutrition.ask_expert",
    locale: "en",
    agentCardUrl: "https://luzia-nexo.thewordlab.net/api/apps/nutrition/agent.json",
  };

  it("renders the default chat icon when no avatar is provided", () => {
    render(
      <AgentChatFab
        chatOptions={chatOptions}
        shellMode="standalone"
        ariaLabel="Open chat"
        renderPanel={() => null}
      />,
    );

    const button = screen.getByRole("button", { name: "Open chat" });
    const image = button.querySelector("img");
    expect(image).toBeNull();
    expect(button.querySelector("svg")).not.toBeNull();
  });

  it("prefers the personality avatar when one is available", () => {
    render(
      <AgentChatFab
        chatOptions={chatOptions}
        shellMode="standalone"
        ariaLabel="Open chat"
        personality={{
          id: "pers-1",
          slug: "trainer",
          name: "Trainer",
          greeting: "Hello",
          suggestions: [],
          assets: { avatarLight: "/avatars/trainer.png" },
          brand: {},
        }}
        renderPanel={() => null}
      />,
    );

    const button = screen.getByRole("button", { name: "Open chat" });
    const image = button.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/avatars/trainer.png");
    expect(screen.getByText("Trainer")).toBeInTheDocument();
  });

  it("prefers the resolved agent appearance over the personality avatar", () => {
    render(
      <AgentChatFab
        chatOptions={chatOptions}
        shellMode="standalone"
        ariaLabel="Open chat"
        personality={{
          id: "pers-1",
          slug: "trainer",
          name: "Trainer",
          greeting: "Hello",
          suggestions: [],
          assets: { avatarLight: "/avatars/trainer.png" },
          brand: {},
        }}
        agentAppearance={{
          displayName: "Elias",
          avatarLight: "/avatars/elias-bra.png",
          variantKey: "team-bra",
        }}
        renderPanel={() => null}
      />,
    );

    const button = screen.getByRole("button", { name: "Open chat" });
    const image = button.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/avatars/elias-bra.png");
    expect(screen.getByText("Elias")).toBeInTheDocument();
  });

  it("still prefers an explicit avatar prop over the resolved agent appearance", () => {
    render(
      <AgentChatFab
        chatOptions={chatOptions}
        shellMode="standalone"
        ariaLabel="Open chat"
        agentAppearance={{
          displayName: "Elias",
          avatarLight: "/avatars/elias-bra.png",
        }}
        avatar="/avatars/manual.png"
        label="Manual"
        renderPanel={() => null}
      />,
    );

    const button = screen.getByRole("button", { name: "Open chat" });
    const image = button.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/avatars/manual.png");
    expect(screen.getByText("Elias")).toBeInTheDocument();
  });

  it("hides the FAB in webview mode", () => {
    const renderPanel = vi.fn();
    render(
      <AgentChatFab
        chatOptions={chatOptions}
        shellMode="webview"
        ariaLabel="Open chat"
        renderPanel={renderPanel}
      />,
    );

    expect(screen.queryByRole("button", { name: "Open chat" })).toBeNull();
    expect(renderPanel).not.toHaveBeenCalled();
  });
});
