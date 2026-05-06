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

  it("uses the Luzia avatar by default in standalone mode", () => {
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
    expect(image).not.toBeNull();
    expect(image?.getAttribute("src")).toBe("./luzia/avatars/luzia-avatar.svg");
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
