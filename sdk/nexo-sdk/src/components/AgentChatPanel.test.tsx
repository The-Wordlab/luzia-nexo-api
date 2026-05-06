import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentChatPanel } from "./AgentChatPanel";
import type { AgentChatPanelProps } from "./AgentChatPanel";

function makeProps(
  overrides: Partial<AgentChatPanelProps> = {},
): AgentChatPanelProps {
  return {
    messages: [],
    suggestions: [
      "Who are the opening match favourites?",
      "Which group looks hardest to predict?",
    ],
    sending: false,
    progress: null,
    error: null,
    onSendMessage: vi.fn(),
    onClearThread: vi.fn(),
    placeholder: "Ask about any match or team...",
    clearLabel: "Clear chat",
    closeLabel: "Close",
    title: "Ask Expert",
    welcomeTitle: "Ask the expert",
    welcomeDescription: "Get help with fast, focused answers.",
    ...overrides,
  };
}

describe("AgentChatPanel", () => {
  it("renders the welcome state with suggestions when the thread is empty", () => {
    render(<AgentChatPanel {...makeProps()} />);

    expect(screen.getByText("Ask Expert")).toBeInTheDocument();
    expect(screen.getByText("Ask the expert")).toBeInTheDocument();
    expect(
      screen.getByText("Get help with fast, focused answers."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Who are the opening match favourites?",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Clear chat" }),
    ).not.toBeInTheDocument();
  });

  it("shows a clear-thread action once messages exist", () => {
    const onClearThread = vi.fn();

    render(
      <AgentChatPanel
        {...makeProps({
          messages: [
            {
              id: "user-1",
              role: "user",
              text: "Who are the favourites?",
              timestamp: Date.now(),
            },
          ],
          onClearThread,
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Clear chat" }));

    expect(onClearThread).toHaveBeenCalledTimes(1);
  });
});
