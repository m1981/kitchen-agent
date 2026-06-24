/**
 * $lib/token_estimator.ts
 * ========================
 * Client-side token estimation using the chars/4 heuristic.
 *
 * Mirrors the backend's `estimate_tokens_for_text()` from `src/token_counter.py`
 * so the UI can show an instant "you are about to send ~N tokens" indicator
 * without making an API call on every keystroke.
 *
 * Rules (matching backend exactly):
 *   Text:           ceil(length / 4)  (≈4 chars per token for Latin/Polish)
 *   Image:          258 tokens per image (conservative single-tile Gemini estimate)
 *   Context files:  Same text heuristic, cached per-file
 *   System prompt:  Same text heuristic, cached on mode change
 *   History:        Last known session token count (from API)
 */

/**
 * Estimate tokens for a plain-text string.
 * Mirrors backend: math.ceil(len(text) / 4)
 */
export function estimateTokensForText(text: string): number {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}

/**
 * Estimate tokens for a single image.
 * Conservative: 258 tokens (1 Gemini vision tile).
 */
export function estimateTokensForImage(): number {
  return 258;
}

/**
 * Estimate total input tokens for a pending message.
 *
 * This is the "what you'll pay when you click Send" number.
 *
 * @param userMessage - The text the user has typed
 * @param imageCount - Number of images attached
 * @param contextFileTokens - Pre-calculated token estimate for attached context files
 * @param systemPromptText - The resolved system prompt for the current mode
 * @param historyTokenCount - Token count of prior conversation history (from session API)
 * @returns Total estimated input tokens
 */
export function estimateInputTokens(
  userMessage: string,
  imageCount: number,
  contextFileTokens: number,
  systemPromptText: string,
  historyTokenCount: number,
): number {
  const textTokens = estimateTokensForText(userMessage);
  const imageTokens = imageCount * estimateTokensForImage();
  const systemPromptTokens = estimateTokensForText(systemPromptText);

  return textTokens + imageTokens + contextFileTokens + systemPromptTokens + historyTokenCount;
}

/**
 * Format a token count for display.
 * Uses K suffix for thousands (e.g. 4,271 → "4.3K", 890 → "890").
 */
export function formatTokenCount(count: number): string {
  if (count >= 10_000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return String(count);
}

/**
 * Calculate context window usage percentage.
 * Returns 0 when contextWindowK is 0 or unknown.
 */
export function contextWindowPercent(usedTokens: number, contextWindowK: number): number {
  if (!contextWindowK) return 0;
  const maxTokens = contextWindowK * 1000;
  return Math.min(100, Math.round((usedTokens / maxTokens) * 100));
}

/**
 * Return a color class based on context window usage.
 *   < 80% → green (safe)
 *  80-95% → yellow (warning)
 *  > 95%  → red (danger)
 */
export function contextWindowColor(pct: number): "safe" | "warn" | "danger" {
  if (pct >= 95) return "danger";
  if (pct >= 80) return "warn";
  return "safe";
}
