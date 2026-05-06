import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ContentBlockRenderer } from "./ContentBlockRenderer";
import {
  registerBlockRenderer,
  clearBlockRenderers,
} from "../content-blocks";
import type { ContentBlock } from "../chat-types";

describe("ContentBlockRenderer", () => {
  beforeEach(() => {
    clearBlockRenderers();
  });

  it("renders text blocks as paragraphs", () => {
    const blocks: ContentBlock[] = [
      { type: "text", text: "Hello world" },
    ];
    render(<ContentBlockRenderer blocks={blocks} />);
    expect(screen.getByText("Hello world")).toBeTruthy();
    expect(screen.getByText("Hello world").tagName).toBe("P");
  });

  it("renders multiple text blocks in order", () => {
    const blocks: ContentBlock[] = [
      { type: "text", text: "First paragraph" },
      { type: "text", text: "Second paragraph" },
    ];
    const { container } = render(<ContentBlockRenderer blocks={blocks} />);
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0].textContent).toBe("First paragraph");
    expect(paragraphs[1].textContent).toBe("Second paragraph");
  });

  it("skips text blocks with no text", () => {
    const blocks: ContentBlock[] = [
      { type: "text" },
      { type: "text", text: "Visible" },
    ];
    const { container } = render(<ContentBlockRenderer blocks={blocks} />);
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });

  it("renders image blocks as img tags", () => {
    const blocks: ContentBlock[] = [
      { type: "image", url: "https://example.com/photo.jpg", alt: "A photo" },
    ];
    render(<ContentBlockRenderer blocks={blocks} />);
    const img = screen.getByAltText("A photo");
    expect(img.tagName).toBe("IMG");
    expect(img.getAttribute("src")).toBe("https://example.com/photo.jpg");
  });

  it("skips image blocks with no url", () => {
    const blocks: ContentBlock[] = [{ type: "image" }];
    const { container } = render(<ContentBlockRenderer blocks={blocks} />);
    expect(container.querySelectorAll("img")).toHaveLength(0);
  });

  it("renders data blocks using registered renderer", () => {
    registerBlockRenderer("test.summary", (block) => (
      <div data-testid="custom-renderer">
        Calories: {(block.data as Record<string, number>)?.calories}
      </div>
    ));

    const blocks: ContentBlock[] = [
      {
        type: "data",
        format: "test.summary",
        data: { calories: 1820 },
      },
    ];
    render(<ContentBlockRenderer blocks={blocks} />);
    expect(screen.getByTestId("custom-renderer")).toBeTruthy();
    expect(screen.getByText("Calories: 1820")).toBeTruthy();
  });

  it("skips data blocks with no registered renderer", () => {
    const blocks: ContentBlock[] = [
      {
        type: "data",
        format: "unknown.format",
        data: { value: 42 },
      },
    ];
    const { container } = render(<ContentBlockRenderer blocks={blocks} />);
    expect(container.querySelector(".nexo-content-blocks")?.children).toHaveLength(0);
  });

  it("skips data blocks with no format", () => {
    const blocks: ContentBlock[] = [
      { type: "data", data: { value: 42 } },
    ];
    const { container } = render(<ContentBlockRenderer blocks={blocks} />);
    expect(container.querySelector(".nexo-content-blocks")?.children).toHaveLength(0);
  });

  it("silently ignores unknown block types", () => {
    const blocks: ContentBlock[] = [
      { type: "future_widget" as string },
      { type: "text", text: "Still visible" },
    ];
    render(<ContentBlockRenderer blocks={blocks} />);
    expect(screen.getByText("Still visible")).toBeTruthy();
  });

  it("falls back to text when all blocks are unregistered", () => {
    const blocks: ContentBlock[] = [
      { type: "data", format: "unknown.format", data: { v: 1 } },
    ];
    render(
      <ContentBlockRenderer blocks={blocks} fallbackText="Fallback text here" />,
    );
    expect(screen.getByText("Fallback text here")).toBeTruthy();
  });

  it("does not fall back when at least one block renders", () => {
    const blocks: ContentBlock[] = [
      { type: "text", text: "Visible block" },
      { type: "data", format: "unknown.format", data: {} },
    ];
    render(
      <ContentBlockRenderer blocks={blocks} fallbackText="Should not appear" />,
    );
    expect(screen.getByText("Visible block")).toBeTruthy();
    expect(screen.queryByText("Should not appear")).toBeNull();
  });

  it("renders mixed block types in order", () => {
    registerBlockRenderer("test.card", () => (
      <div data-testid="test-card">Card</div>
    ));

    const blocks: ContentBlock[] = [
      { type: "text", text: "Before the card" },
      { type: "data", format: "test.card", data: {} },
      { type: "text", text: "After the card" },
    ];
    const { container } = render(<ContentBlockRenderer blocks={blocks} />);
    const children = container.querySelector(".nexo-content-blocks")?.children;
    expect(children).toHaveLength(3);
    expect(children?.[0].textContent).toBe("Before the card");
    expect(children?.[1].getAttribute("data-testid")).toBe("test-card");
    expect(children?.[2].textContent).toBe("After the card");
  });
});
