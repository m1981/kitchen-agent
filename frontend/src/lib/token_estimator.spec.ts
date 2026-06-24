import { describe, it, expect } from "vitest";
import {
  estimateTokensForText,
  estimateTokensForImage,
  estimateInputTokens,
  formatTokenCount,
  contextWindowPercent,
  contextWindowColor,
} from "./token_estimator";

describe("estimateTokensForText", () => {
  it("returns 0 for empty string", () => {
    expect(estimateTokensForText("")).toBe(0);
  });

  it("returns proportional count for normal text", () => {
    // 400 chars / 4 = 100 tokens
    const result = estimateTokensForText("a".repeat(400));
    expect(result).toBe(100);
  });

  it("ceils fractional results", () => {
    // 5 chars / 4 = 1.25 → ceil = 2
    expect(estimateTokensForText("hello")).toBe(2);
  });

  it("returns integer", () => {
    expect(typeof estimateTokensForText("test")).toBe("number");
    expect(Number.isInteger(estimateTokensForText("test"))).toBe(true);
  });

  it("longer text gives higher count", () => {
    const short = estimateTokensForText("hi");
    const long = estimateTokensForText("hi ".repeat(100));
    expect(long).toBeGreaterThan(short);
  });
});

describe("estimateTokensForImage", () => {
  it("returns 258 (single Gemini tile)", () => {
    expect(estimateTokensForImage()).toBe(258);
  });
});

describe("estimateInputTokens", () => {
  it("calculates sum of all components", () => {
    const result = estimateInputTokens(
      "hello world", // 11 chars → 3 tokens
      2, // 2 images → 516 tokens
      100, // context files → 100 tokens
      "You are helpful", // 16 chars → 4 tokens
      500, // history → 500 tokens
    );
    expect(result).toBe(3 + 516 + 100 + 4 + 500); // 1123
  });

  it("handles empty message with no extras", () => {
    const result = estimateInputTokens("", 0, 0, "", 0);
    expect(result).toBe(0);
  });

  it("handles only history tokens", () => {
    const result = estimateInputTokens("", 0, 0, "", 2000);
    expect(result).toBe(2000);
  });

  it("handles message with images only", () => {
    const result = estimateInputTokens("hi", 3, 0, "", 0);
    expect(result).toBe(1 + 3 * 258); // 775
  });
});

describe("formatTokenCount", () => {
  it("shows plain number under 1000", () => {
    expect(formatTokenCount(890)).toBe("890");
  });

  it("shows K suffix for thousands", () => {
    expect(formatTokenCount(4271)).toBe("4.3K");
  });

  it("shows K suffix for 10K+", () => {
    expect(formatTokenCount(15000)).toBe("15.0K");
  });

  it('shows 0 as "0"', () => {
    expect(formatTokenCount(0)).toBe("0");
  });
});

describe("contextWindowPercent", () => {
  it("returns 0 for zero context window", () => {
    expect(contextWindowPercent(500, 0)).toBe(0);
  });

  it("calculates percentage correctly", () => {
    // 50K tokens used out of 200K context = 25%
    expect(contextWindowPercent(50_000, 200)).toBe(25);
  });

  it("caps at 100%", () => {
    expect(contextWindowPercent(500_000, 200)).toBe(100);
  });
});

describe("contextWindowColor", () => {
  it("returns safe under 80%", () => {
    expect(contextWindowColor(50)).toBe("safe");
  });

  it("returns warn at 80-94%", () => {
    expect(contextWindowColor(80)).toBe("warn");
    expect(contextWindowColor(94)).toBe("warn");
  });

  it("returns danger at 95%+", () => {
    expect(contextWindowColor(95)).toBe("danger");
    expect(contextWindowColor(100)).toBe("danger");
  });
});
