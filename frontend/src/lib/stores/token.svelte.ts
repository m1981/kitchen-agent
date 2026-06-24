/**
 * lib/stores/token.svelte.ts
 * ============================
 * Rune-based store for token counting and estimation.
 *
 * Responsibilities:
 *   - Session token count (from backend /api/sessions/{id}/tokens)
 *   - Context file token estimate (client-side chars/4)
 *   - Cached system prompt text for estimation
 *   - Live input token estimate (what you'll pay when you click Send)
 *
 * Cross-store reads (passed as args, not imported):
 *   - pastedImages count (from chatMessagingStore)
 *   - contextFiles (from chatMessagingStore)
 *   - selectedModeId (from promptStore)
 */

import { api } from "$lib/api";
import type { PastedImage } from "$lib/types";
import { estimateTokensForText, estimateTokensForImage } from "$lib/token_estimator";

function createTokenStore() {
  let sessionTokenCount = $state<number>(-1);
  let sessionTokenFallback = $state<boolean>(false);
  let contextFileTokenEstimate = $state<number>(0);
  let cachedSystemPromptText = $state<string>("");

  return {
    get sessionTokenCount() {
      return sessionTokenCount;
    },
    get sessionTokenFallback() {
      return sessionTokenFallback;
    },
    get contextFileTokenEstimate() {
      return contextFileTokenEstimate;
    },

    /**
     * Reactive input token estimate — "what you'll pay when you click Send".
     * Computed client-side using the chars/4 heuristic for instant feedback.
     */
    estimateInputTokensFor(
      messageText: string,
      imageCount: number,
      contextFileTokens: number,
    ): number {
      const textTokens = estimateTokensForText(messageText);
      const imageTokens = imageCount * estimateTokensForImage();
      const systemPromptTokens = estimateTokensForText(cachedSystemPromptText);
      const historyTokens = Math.max(0, sessionTokenCount);

      return textTokens + imageTokens + contextFileTokens + systemPromptTokens + historyTokens;
    },

    /**
     * Fetch the session's token count from the backend API.
     * Called automatically after each send and on session load.
     */
    async refreshSessionTokens(sessionId: string) {
      try {
        const data = await api.getSessionTokens(sessionId);
        sessionTokenCount = data.total_tokens;
        sessionTokenFallback = data.fallback_used;
      } catch {
        // Backend not available — keep previous value
      }
    },

    /**
     * Refresh the cached context file token estimate.
     * Called when contextFiles changes.
     */
    async refreshContextFileTokens(contextFiles: string[]) {
      if (contextFiles.length === 0) {
        contextFileTokenEstimate = 0;
        return;
      }
      let total = 0;
      for (const path of contextFiles) {
        try {
          const data = await api.readFile(path);
          total += estimateTokensForText(data.content);
        } catch {
          // Unreadable file — skip
        }
      }
      contextFileTokenEstimate = total;
    },

    /**
     * Refresh the cached system prompt text for token estimation.
     * Called when the mode changes.
     */
    async refreshCachedSystemPrompt(modeId: string) {
      try {
        const detail = await api.getPromptModeDetail(modeId);
        cachedSystemPromptText = detail.content ?? "";
      } catch {
        cachedSystemPromptText = "";
      }
    },

    /** Reset token state. Called on startNewChat. */
    reset() {
      sessionTokenCount = -1;
      sessionTokenFallback = false;
      contextFileTokenEstimate = 0;
      cachedSystemPromptText = "";
    },
  };
}

export const tokenStore = createTokenStore();
