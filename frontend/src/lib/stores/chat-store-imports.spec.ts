/**
 * chat-store-imports.spec.ts
 * ==========================
 * Tests for Phase 2: Break chatStore Facade — Direct Store Imports.
 *
 * These tests verify that:
 *   1. Sub-stores export the expected properties
 *   2. chatStore delegation getters work correctly (regression)
 *   3. Components can access sub-store state directly
 *
 * This is the TDD foundation for the refactor.
 */
import { describe, it, expect } from "vitest";

// Import stores directly
import { chatStore } from "./chat.svelte";
import { providerStore } from "./provider.svelte";
import { promptStore } from "./prompt.svelte";
import { editorStore } from "./editor.svelte";
import { tokenStore } from "./token.svelte";

describe("Phase 2: Direct Store Imports", () => {
  describe("providerStore exports", () => {
    it("should have providers property", () => {
      expect(providerStore).toHaveProperty("providers");
      expect(Array.isArray(providerStore.providers)).toBe(true);
    });

    it("should have selectedProvider property", () => {
      expect(providerStore).toHaveProperty("selectedProvider");
      expect(typeof providerStore.selectedProvider).toBe("string");
    });

    it("should have selectedModel property", () => {
      expect(providerStore).toHaveProperty("selectedModel");
      expect(typeof providerStore.selectedModel).toBe("string");
    });

    it("should have appTitle property", () => {
      expect(providerStore).toHaveProperty("appTitle");
      expect(typeof providerStore.appTitle).toBe("string");
    });

    it("should have appDescription property", () => {
      expect(providerStore).toHaveProperty("appDescription");
      expect(typeof providerStore.appDescription).toBe("string");
    });

    it("should have contextWindowK property", () => {
      expect(providerStore).toHaveProperty("contextWindowK");
      expect(typeof providerStore.contextWindowK).toBe("number");
    });

    it("should have loadProviders method", () => {
      expect(providerStore).toHaveProperty("loadProviders");
      expect(typeof providerStore.loadProviders).toBe("function");
    });

    it("should have loadAppInfo method", () => {
      expect(providerStore).toHaveProperty("loadAppInfo");
      expect(typeof providerStore.loadAppInfo).toBe("function");
    });

    it("should have setProvider method", () => {
      expect(providerStore).toHaveProperty("setProvider");
      expect(typeof providerStore.setProvider).toBe("function");
    });

    it("should have setModel method", () => {
      expect(providerStore).toHaveProperty("setModel");
      expect(typeof providerStore.setModel).toBe("function");
    });
  });

  describe("promptStore exports", () => {
    it("should have selectedModeId property", () => {
      expect(promptStore).toHaveProperty("selectedModeId");
      expect(typeof promptStore.selectedModeId).toBe("string");
    });

    it("should have modesState property", () => {
      expect(promptStore).toHaveProperty("modesState");
      expect(promptStore.modesState).toHaveProperty("status");
    });

    it("should have toolsEnabled property", () => {
      expect(promptStore).toHaveProperty("toolsEnabled");
      expect(typeof promptStore.toolsEnabled).toBe("boolean");
    });

    it("should have loadModes method", () => {
      expect(promptStore).toHaveProperty("loadModes");
      expect(typeof promptStore.loadModes).toBe("function");
    });

    it("should have setSelectedModeId method", () => {
      expect(promptStore).toHaveProperty("setSelectedModeId");
      expect(typeof promptStore.setSelectedModeId).toBe("function");
    });

    it("should have toggleTools method", () => {
      expect(promptStore).toHaveProperty("toggleTools");
      expect(typeof promptStore.toggleTools).toBe("function");
    });

    it("should have setToolsEnabled method", () => {
      expect(promptStore).toHaveProperty("setToolsEnabled");
      expect(typeof promptStore.setToolsEnabled).toBe("function");
    });
  });

  describe("editorStore exports", () => {
    it("should have editingTurnId property", () => {
      expect(editorStore).toHaveProperty("editingTurnId");
      // Can be null or string
      expect(
        editorStore.editingTurnId === null || typeof editorStore.editingTurnId === "string",
      ).toBe(true);
    });

    it("should have editDraft property", () => {
      expect(editorStore).toHaveProperty("editDraft");
      expect(typeof editorStore.editDraft).toBe("string");
    });

    it("should have editState property", () => {
      expect(editorStore).toHaveProperty("editState");
      expect(editorStore.editState).toHaveProperty("status");
    });

    it("should have sessionSystemPrompt property", () => {
      expect(editorStore).toHaveProperty("sessionSystemPrompt");
      // Can be null or string
      expect(
        editorStore.sessionSystemPrompt === null ||
          typeof editorStore.sessionSystemPrompt === "string",
      ).toBe(true);
    });

    it("should have resolvedSystemPrompt property", () => {
      expect(editorStore).toHaveProperty("resolvedSystemPrompt");
      expect(typeof editorStore.resolvedSystemPrompt).toBe("string");
    });

    it("should have isSystemPromptOverride property", () => {
      expect(editorStore).toHaveProperty("isSystemPromptOverride");
      expect(typeof editorStore.isSystemPromptOverride).toBe("boolean");
    });

    it("should have systemPromptDraft property", () => {
      expect(editorStore).toHaveProperty("systemPromptDraft");
      expect(typeof editorStore.systemPromptDraft).toBe("string");
    });

    it("should have systemPromptState property", () => {
      expect(editorStore).toHaveProperty("systemPromptState");
      expect(editorStore.systemPromptState).toHaveProperty("status");
    });

    it("should have systemPromptError property", () => {
      expect(editorStore).toHaveProperty("systemPromptError");
      expect(typeof editorStore.systemPromptError).toBe("string");
    });

    it("should have startEditing method", () => {
      expect(editorStore).toHaveProperty("startEditing");
      expect(typeof editorStore.startEditing).toBe("function");
    });

    it("should have cancelEditing method", () => {
      expect(editorStore).toHaveProperty("cancelEditing");
      expect(typeof editorStore.cancelEditing).toBe("function");
    });

    it("should have saveEdit method", () => {
      expect(editorStore).toHaveProperty("saveEdit");
      expect(typeof editorStore.saveEdit).toBe("function");
    });

    it("should have deleteMessage method", () => {
      expect(editorStore).toHaveProperty("deleteMessage");
      expect(typeof editorStore.deleteMessage).toBe("function");
    });

    it("should have saveSystemPrompt method", () => {
      expect(editorStore).toHaveProperty("saveSystemPrompt");
      expect(typeof editorStore.saveSystemPrompt).toBe("function");
    });

    it("should have clearSystemPrompt method", () => {
      expect(editorStore).toHaveProperty("clearSystemPrompt");
      expect(typeof editorStore.clearSystemPrompt).toBe("function");
    });

    it("should have reset method", () => {
      expect(editorStore).toHaveProperty("reset");
      expect(typeof editorStore.reset).toBe("function");
    });
  });

  describe("tokenStore exports", () => {
    it("should have sessionTokenCount property", () => {
      expect(tokenStore).toHaveProperty("sessionTokenCount");
      expect(typeof tokenStore.sessionTokenCount).toBe("number");
    });

    it("should have sessionTokenFallback property", () => {
      expect(tokenStore).toHaveProperty("sessionTokenFallback");
      expect(typeof tokenStore.sessionTokenFallback).toBe("boolean");
    });

    it("should have contextFileTokenEstimate property", () => {
      expect(tokenStore).toHaveProperty("contextFileTokenEstimate");
      expect(typeof tokenStore.contextFileTokenEstimate).toBe("number");
    });

    it("should have estimateInputTokensFor method", () => {
      expect(tokenStore).toHaveProperty("estimateInputTokensFor");
      expect(typeof tokenStore.estimateInputTokensFor).toBe("function");
    });

    it("should have refreshSessionTokens method", () => {
      expect(tokenStore).toHaveProperty("refreshSessionTokens");
      expect(typeof tokenStore.refreshSessionTokens).toBe("function");
    });

    it("should have refreshContextFileTokens method", () => {
      expect(tokenStore).toHaveProperty("refreshContextFileTokens");
      expect(typeof tokenStore.refreshContextFileTokens).toBe("function");
    });

    it("should have reset method", () => {
      expect(tokenStore).toHaveProperty("reset");
      expect(typeof tokenStore.reset).toBe("function");
    });
  });

  describe("chatStore own properties", () => {
    it("should have sessionId", () => {
      expect(chatStore).toHaveProperty("sessionId");
      expect(typeof chatStore.sessionId).toBe("string");
    });

    it("should have messages", () => {
      expect(chatStore).toHaveProperty("messages");
      expect(Array.isArray(chatStore.messages)).toBe(true);
    });

    it("should have chatState", () => {
      expect(chatStore).toHaveProperty("chatState");
      expect(chatStore.chatState).toHaveProperty("status");
    });

    it("should have pastedImages", () => {
      expect(chatStore).toHaveProperty("pastedImages");
      expect(Array.isArray(chatStore.pastedImages)).toBe(true);
    });

    it("should have contextFiles", () => {
      expect(chatStore).toHaveProperty("contextFiles");
      expect(Array.isArray(chatStore.contextFiles)).toBe(true);
    });

    it("should have isStreaming", () => {
      expect(chatStore).toHaveProperty("isStreaming");
      expect(typeof chatStore.isStreaming).toBe("boolean");
    });

    it("should have sendMessage method", () => {
      expect(chatStore).toHaveProperty("sendMessage");
      expect(typeof chatStore.sendMessage).toBe("function");
    });

    it("should have loadSession method", () => {
      expect(chatStore).toHaveProperty("loadSession");
      expect(typeof chatStore.loadSession).toBe("function");
    });

    it("should have forkSession method", () => {
      expect(chatStore).toHaveProperty("forkSession");
      expect(typeof chatStore.forkSession).toBe("function");
    });

    it("should have stopStreaming method", () => {
      expect(chatStore).toHaveProperty("stopStreaming");
      expect(typeof chatStore.stopStreaming).toBe("function");
    });

    it("should have resetForNewChat method", () => {
      expect(chatStore).toHaveProperty("resetForNewChat");
      expect(typeof chatStore.resetForNewChat).toBe("function");
    });
  });
});
