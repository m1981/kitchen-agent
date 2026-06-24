<script lang="ts">
  /**
   * TokenIndicator
   * ==============
   * Minimal colored strip bar showing context window usage.
   *
   * Color thresholds:
   *   < 10% → no bar (hidden)
   *   10-20% → yellow
   *   20-30% → orange
   *   > 30% → red
   */

  import { tokenStore } from "$lib/stores/token.svelte";
  import { providerStore } from "$lib/stores/provider.svelte";
  import { contextWindowPercent } from "$lib/token_estimator";

  type Props = {
    /** Current message text in the composer (for input token estimation). */
    messageText: string;
  };

  let { messageText }: Props = $props();

  const inputTokens = $derived(
    tokenStore.estimateInputTokensFor(messageText, 0, tokenStore.contextFileTokenEstimate),
  );

  const pct = $derived(contextWindowPercent(inputTokens, providerStore.contextWindowK));

  // Strip color: hidden below 10%, then yellow → orange → red
  const stripColor = $derived(
    pct > 30 ? "bg-red-500" : pct > 20 ? "bg-orange-400" : pct > 10 ? "bg-yellow-400" : "",
  );

  const showStrip = $derived(pct > 10);
</script>

{#if showStrip}
  <div class="px-3 pt-1.5">
    <div
      data-testid="token-strip"
      class="h-1 w-full overflow-hidden rounded-full bg-line"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Context window usage: {pct}%"
    >
      <div
        class="h-full rounded-full transition-all duration-300 {stripColor}"
        style="width: {Math.min(100, pct)}%;"
      ></div>
    </div>
  </div>
{/if}
