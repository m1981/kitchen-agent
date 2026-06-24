<script lang="ts">
  /**
   * CreateFolderDialog
   * ==================
   * Modal dialog for creating a new folder with name, color, and icon.
   */
  import type { FolderCreateRequest } from "$lib/api";
  import Dialog from "./ui/Dialog.svelte";

  type Props = {
    onclose: () => void;
    oncreate: (request: FolderCreateRequest) => void;
  };

  let { onclose, oncreate }: Props = $props();

  let name = $state("");
  let selectedColor = $state("#3B82F6");
  let selectedIcon = $state("📁");
  let nameError = $state("");

  const colors = [
    { name: "Gray", hex: "#6B7280" },
    { name: "Red", hex: "#EF4444" },
    { name: "Orange", hex: "#F97316" },
    { name: "Yellow", hex: "#EAB308" },
    { name: "Green", hex: "#22C55E" },
    { name: "Blue", hex: "#3B82F6" },
    { name: "Purple", hex: "#A855F7" },
    { name: "Pink", hex: "#EC4899" },
  ];

  const icons = ["📁", "🍳", "🏠", "🛋️", "🚿", "🪑", "💡", "🎨", "📐", "🔧", "📋", "⭐"];

  function validate(): boolean {
    if (!name.trim()) {
      nameError = "Folder name is required";
      return false;
    }
    if (name.length > 100) {
      nameError = "Name must be 100 characters or less";
      return false;
    }
    nameError = "";
    return true;
  }

  function handleSubmit() {
    if (!validate()) return;
    oncreate({
      name: name.trim(),
      color: selectedColor,
      icon: selectedIcon,
    });
  }
</script>

<Dialog open={true} {onclose} title="Create Folder">
  <!-- Name input -->
  <div class="mb-4">
    <label for="folder-name" class="mb-1 block text-sm font-medium text-ink"> Name </label>
    <input
      id="folder-name"
      type="text"
      bind:value={name}
      placeholder="e.g., Kitchen Projects"
      maxlength="100"
      class="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none {nameError
        ? 'border-red-500'
        : ''}"
    />
    {#if nameError}
      <p class="mt-1 text-xs text-red-600">{nameError}</p>
    {/if}
  </div>

  <!-- Color picker -->
  <div class="mb-4">
    <p class="mb-2 text-sm font-medium text-ink">Color</p>
    <div class="flex gap-2">
      {#each colors as color (color.hex)}
        <button
          type="button"
          onclick={() => (selectedColor = color.hex)}
          class="h-8 w-8 rounded-full transition-transform hover:scale-110 {selectedColor ===
          color.hex
            ? 'ring-2 ring-accent ring-offset-2'
            : ''}"
          style="background-color: {color.hex}"
          aria-label={color.name}
          title={color.name}
        ></button>
      {/each}
    </div>
  </div>

  <!-- Icon picker -->
  <div class="mb-6">
    <p class="mb-2 text-sm font-medium text-ink">Icon</p>
    <div class="flex flex-wrap gap-2">
      {#each icons as icon (icon)}
        <button
          type="button"
          onclick={() => (selectedIcon = icon)}
          class="flex h-10 w-10 items-center justify-center rounded-lg border border-line text-xl transition hover:bg-surface {selectedIcon ===
          icon
            ? 'border-accent bg-accent/10'
            : ''}"
          aria-label={icon}
        >
          {icon}
        </button>
      {/each}
    </div>
  </div>

  <!-- Preview -->
  <div class="mb-4 rounded-lg border border-line bg-surface p-3">
    <p class="mb-1 text-xs text-muted">Preview</p>
    <div class="flex items-center gap-2">
      <span class="h-4 w-4 rounded-full" style="background-color: {selectedColor}"></span>
      <span class="text-sm text-ink">
        {selectedIcon}
        {name || "Folder Name"}
      </span>
    </div>
  </div>

  {#snippet footer()}
    <button
      type="button"
      onclick={onclose}
      class="rounded-md border border-line px-4 py-2 text-sm text-ink transition hover:bg-surface"
    >
      Cancel
    </button>
    <button
      type="button"
      onclick={handleSubmit}
      class="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent/90"
    >
      Create Folder
    </button>
  {/snippet}
</Dialog>
