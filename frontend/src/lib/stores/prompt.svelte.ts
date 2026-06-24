/**
 * lib/stores/prompt.svelte.ts
 * =============================
 * Rune-based store for prompt modes and tools toggle.
 *
 * Responsibilities:
 *   - Prompt mode list (loaded from /api/prompts/modes)
 *   - Selected mode ID
 *   - Tools enabled toggle (synced to mode default, user-overridable)
 *
 * Independent — no cross-store dependencies.
 */

import { api, type PromptMode } from "$lib/api";
import type { AsyncState } from "$lib/types";
import { persisted } from "$lib/persist.svelte";

function createPromptStore() {
  const selectedModeId = persisted<string>("ka:mode", "general");
  let modesState = $state<AsyncState<void>>({ status: "idle" });
  const toolsEnabled = persisted<boolean>("ka:tools", true);

  return {
    get selectedModeId() {
      return selectedModeId.current;
    },
    get modesState() {
      return modesState;
    },
    get toolsEnabled() {
      return toolsEnabled.current;
    },

    async loadModes(): Promise<PromptMode[]> {
      if (modesState.status === "loading") return [];
      modesState = { status: "loading" };
      try {
        const fetched = await api.getPromptModes();
        modesState = { status: "success", data: undefined };
        // Keep selectedModeId when still valid, otherwise fall back to first.
        let modeReset = false;
        if (fetched.length > 0 && !fetched.find((m) => m.id === selectedModeId.current)) {
          selectedModeId.current = fetched[0].id;
          modeReset = true;
        }
        // Sync toolsEnabled to mode default only when the mode was just reset
        // (i.e. the persisted mode no longer exists). Otherwise respect the
        // user's persisted toggle choice.
        if (modeReset) {
          const activeModeData = fetched.find((m) => m.id === selectedModeId.current);
          if (activeModeData !== undefined)
            toolsEnabled.current = activeModeData.tools_enabled_default ?? true;
        }
        return fetched;
      } catch (e) {
        console.error("Failed to load prompt modes", e);
        modesState = { status: "error", message: String(e) };
        return [];
      }
    },

    setSelectedModeId(id: string, modes?: PromptMode[]) {
      if (id === selectedModeId.current) return;
      selectedModeId.current = id;
      // Sync toolsEnabled to the new mode's default when provided.
      if (modes) {
        const mode = modes.find((m) => m.id === id);
        if (mode !== undefined) toolsEnabled.current = mode.tools_enabled_default ?? true;
      }
    },

    toggleTools() {
      toolsEnabled.current = !toolsEnabled.current;
    },

    setToolsEnabled(value: boolean) {
      toolsEnabled.current = value;
    },

    /** Reset to defaults. Called on startNewChat. */
    reset() {
      // Mode and tools persist across chats — nothing to reset.
    },
  };
}

export const promptStore = createPromptStore();
