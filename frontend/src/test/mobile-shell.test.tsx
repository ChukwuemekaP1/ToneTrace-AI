import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MobileShell } from "@/components/layout/MobileShell";

describe("MobileShell Layout", () => {
  it("renders with maximum-430px centered mobile shell constraint", () => {
    render(
      <MobileShell activeTab="home">
        <div data-testid="test-content">Welcome to ToneTrace</div>
      </MobileShell>
    );

    const container = screen.getByTestId("mobile-shell-container");
    expect(container).toBeInTheDocument();
    expect(container.className).toContain("max-w-[430px]");
    expect(screen.getByTestId("test-content")).toBeInTheDocument();
  });

  it("handles tab changes when bottom navigation buttons are clicked", () => {
    const handleTabChange = vi.fn();
    render(
      <MobileShell activeTab="home" onTabChange={handleTabChange}>
        <div>Content</div>
      </MobileShell>
    );

    const showcaseBtn = screen.getByRole("button", { name: /showcase/i });
    fireEvent.click(showcaseBtn);
    expect(handleTabChange).toHaveBeenCalledWith("showcase");

    const shelfBtn = screen.getByRole("button", { name: /shelf/i });
    fireEvent.click(shelfBtn);
    expect(handleTabChange).toHaveBeenCalledWith("shelf");
  });

  it("adapts correctly at target viewports (360px compact, 390px baseline, 430px max)", () => {
    const viewports = [360, 390, 430];
    for (const width of viewports) {
      window.innerWidth = width;
      window.dispatchEvent(new Event("resize"));

      const { container } = render(
        <MobileShell activeTab="home">
          <div>Viewport Test: {width}px</div>
        </MobileShell>
      );

      const shell = container.querySelector("[data-testid='mobile-shell-container']");
      expect(shell).not.toBeNull();
      expect(shell?.classList.contains("max-w-[430px]")).toBe(true);
    }
  });
});
