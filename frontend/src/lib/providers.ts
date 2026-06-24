/**
 * src/lib/providers.ts
 * =====================
 * Static catalog of available LLM providers and their model lists.
 *
 * This is the v1 "hardcoded" approach from §7 of the provider integration guide.
 * Once the backend exposes GET /api/providers, this catalog will be replaced
 * by a live fetch — but it is used as the fallback and initial seed.
 *
 * To add a new model: extend the `models` array for the relevant provider.
 * To add a new provider: push a new entry to PROVIDERS.
 */

export type ModelInfo = {
  id: string;
  label: string;
  context_k: number; // context window in thousands of tokens
};

export type ProviderInfo = {
  id: string;
  label: string;
  default_model: string;
  models: ModelInfo[];
};

export const PROVIDERS: ProviderInfo[] = [
  {
    id: "gemini",
    label: "Google Gemini",
    default_model: "gemini-3.1-pro-preview",
    models: [
      { id: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro", context_k: 1000 },
      { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash", context_k: 1000 },
    ],
  },
  {
    id: "anthropic",
    label: "Anthropic Claude",
    default_model: "claude-sonnet-4-6",
    models: [
      { id: "claude-opus-4-8", label: "Claude Opus 4.8", context_k: 200 },
      { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", context_k: 200 },
    ],
  },
  {
    id: "mimo",
    label: "Xiaomi MiMo",
    default_model: "mimo-v2.5-pro",
    models: [
      { id: "mimo-v2.5-pro", label: "MiMo V2.5 Pro", context_k: 1000 },
      { id: "mimo-v2.5", label: "MiMo V2.5", context_k: 1000 },
    ],
  },
];

/** Look up a provider entry by id. Returns undefined when not found. */
export function findProvider(id: string): ProviderInfo | undefined {
  return PROVIDERS.find((p) => p.id === id);
}

/** Look up a model inside a specific provider. Returns undefined when not found. */
export function findModel(providerId: string, modelId: string): ModelInfo | undefined {
  return findProvider(providerId)?.models.find((m) => m.id === modelId);
}
