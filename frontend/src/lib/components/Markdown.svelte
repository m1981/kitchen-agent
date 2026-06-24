<script lang="ts">
  import { tick } from "svelte";
  import { parseMarkdown } from "$lib/markdown";

  let { content, variant = "assistant" } = $props<{
    content: string;
    variant?: "assistant" | "user";
  }>();

  let containerEl = $state<HTMLDivElement | null>(null);
  const rendered = $derived(parseMarkdown(content));

  $effect(() => {
    const htmlSnapshot = rendered;

    tick().then(async () => {
      if (!containerEl || !htmlSnapshot) return;

      const mermaidBlocks = containerEl.querySelectorAll("code.language-mermaid");
      if (mermaidBlocks.length === 0) return;

      const { default: mermaid } = await import("mermaid");

      mermaid.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "strict",
      });

      mermaidBlocks.forEach(async (block, i) => {
        const graphDefinition = block.textContent ?? "";
        const id = `mermaid-${Date.now()}-${i}`;

        try {
          const { svg } = await mermaid.render(id, graphDefinition);
          const wrapper = block.closest("pre") ?? block;
          wrapper.outerHTML = `<div class="mermaid-diagram">${svg}</div>`;
        } catch (e) {
          console.error("Mermaid render error:", e);
        }
      });
    });
  });
</script>

<div bind:this={containerEl} class="markdown-body markdown-body-{variant}">
  <!-- eslint-disable-next-line svelte/no-at-html-tags -->
  {@html rendered}
</div>
