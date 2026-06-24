/**
 * sidebar-resize.svelte.ts
 *
 * Svelte 5 rune-based drag-to-resize logic for left and right sidebars
 * plus the prompt composer. Sizes are persisted to localStorage so they
 * survive page reloads.
 *
 * Usage (in a Svelte component):
 *   import { createSidebarResize } from '$lib/sidebar-resize.svelte';
 *   const resize = createSidebarResize();
 *
 *   // Bind widths
 *   style="width: {resize.leftWidth}px"
 *   style="width: {resize.rightWidth}px"
 *
 *   // Attach drag handles
 *   onmousedown={resize.startLeftDrag}
 *   onmousedown={resize.startRightDrag}
 */

import { SvelteURLSearchParams } from "svelte/reactivity";

const STORAGE_KEY_LEFT = "kitchen-agent:layout:left-sidebar-width";
const STORAGE_KEY_RIGHT = "kitchen-agent:layout:right-sidebar-width";
const STORAGE_KEY_SHOW = "kitchen-agent:layout:right-sidebar-visible";
const STORAGE_KEY_SHOW_LEFT = "kitchen-agent:layout:left-sidebar-visible";
const STORAGE_KEY_PROMPT = "kitchen-agent:layout:prompt-height";
const URL_PARAM_BY_KEY: Record<string, string> = {
  [STORAGE_KEY_LEFT]: "kaLeftSidebar",
  [STORAGE_KEY_RIGHT]: "kaRightSidebar",
  [STORAGE_KEY_SHOW]: "kaRightPanel",
  [STORAGE_KEY_PROMPT]: "kaPromptHeight",
};

const LEFT_MIN = 180;
const LEFT_MAX = 480;
const RIGHT_MIN = 220;
const RIGHT_MAX = 600;
const PROMPT_MIN = 64;
const PROMPT_MAX = 320;

const DEFAULT_LEFT = 256; // w-64 = 16rem = 256px
const DEFAULT_RIGHT = 288; // w-72 = 18rem = 288px
const DEFAULT_PROMPT = 96;

function isStorage(value: unknown): value is Storage {
  return (
    typeof value === "object" &&
    value !== null &&
    "getItem" in value &&
    "setItem" in value &&
    "removeItem" in value &&
    typeof value.getItem === "function" &&
    typeof value.setItem === "function" &&
    typeof value.removeItem === "function"
  );
}

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;

  try {
    const storage = window.localStorage;
    if (!isStorage(storage)) return null;

    const testKey = "kitchen-agent:layout:storage-test";
    storage.setItem(testKey, "1");
    const works = storage.getItem(testKey) === "1";
    storage.removeItem(testKey);
    return works ? storage : null;
  } catch {
    return null;
  }
}

function getCookieDocument(): Document | null {
  return typeof document === "undefined" ? null : document;
}

function readCookie(key: string): string | null {
  const cookieDocument = getCookieDocument();
  if (!cookieDocument) return null;

  try {
    const encodedKey = encodeURIComponent(key);
    const match = cookieDocument.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith(`${encodedKey}=`));

    return match ? decodeURIComponent(match.slice(encodedKey.length + 1)) : null;
  } catch {
    return null;
  }
}

function writeCookie(key: string, value: string) {
  const cookieDocument = getCookieDocument();
  if (!cookieDocument) return;

  try {
    cookieDocument.cookie = `${encodeURIComponent(key)}=${encodeURIComponent(value)}; Path=/; Max-Age=31536000; SameSite=Lax`;
  } catch {
    // Some embedded browser surfaces expose document.cookie as readonly.
  }
}

function readUrlSetting(key: string): string | null {
  if (typeof window === "undefined") return null;
  const param = URL_PARAM_BY_KEY[key];
  if (!param) return null;

  const url = new URL(window.location.href);
  return url.searchParams.get(param) ?? new URLSearchParams(url.hash.slice(1)).get(param);
}

function writeUrlSetting(key: string, value: string) {
  if (typeof window === "undefined") return;
  const param = URL_PARAM_BY_KEY[key];
  if (!param) return;

  try {
    const url = new URL(window.location.href);
    url.searchParams.set(param, value);
    window.history.replaceState(window.history.state, "", url);

    const hashParams = new SvelteURLSearchParams(window.location.hash.slice(1));
    hashParams.set(param, value);
    window.location.hash = hashParams.toString();
  } catch {
    // URL persistence is only a last-resort fallback.
  }
}

function readSetting(key: string): string | null {
  return getStorage()?.getItem(key) ?? readCookie(key) ?? readUrlSetting(key);
}

function writeSetting(key: string, value: string) {
  const storage = getStorage();
  if (storage) {
    try {
      storage.setItem(key, value);
    } catch {
      // Fall through to the secondary persistence paths below.
    }
  }

  writeCookie(key, value);
  writeUrlSetting(key, value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStorage(key: string, fallback: number, min: number, max: number): number {
  const raw = readSetting(key);
  if (!raw) return fallback;
  const n = parseInt(raw, 10);
  return isNaN(n) ? fallback : clamp(n, min, max);
}

function readBoolStorage(key: string, fallback: boolean): boolean {
  const raw = readSetting(key);
  if (raw === null) return fallback;
  return raw === "true";
}

export function createSidebarResize() {
  // ── Persistent widths ────────────────────────────────────────────────────
  let leftWidth = $state(readStorage(STORAGE_KEY_LEFT, DEFAULT_LEFT, LEFT_MIN, LEFT_MAX));
  let rightWidth = $state(readStorage(STORAGE_KEY_RIGHT, DEFAULT_RIGHT, RIGHT_MIN, RIGHT_MAX));
  let promptHeight = $state(
    readStorage(STORAGE_KEY_PROMPT, DEFAULT_PROMPT, PROMPT_MIN, PROMPT_MAX),
  );
  let showLeft = $state(readBoolStorage(STORAGE_KEY_SHOW_LEFT, false));
  let showRight = $state(readBoolStorage(STORAGE_KEY_SHOW, true));

  // ── Drag state (not persisted) ────────────────────────────────────────────
  let dragging: "left" | "right" | "prompt" | null = null;
  let dragStartPosition = 0;
  let dragStartSize = 0;

  // ── Setters ───────────────────────────────────────────────────────────────
  function setLeftWidth(width: number) {
    leftWidth = clamp(width, LEFT_MIN, LEFT_MAX);
    writeSetting(STORAGE_KEY_LEFT, String(leftWidth));
  }

  function setRightWidth(width: number) {
    rightWidth = clamp(width, RIGHT_MIN, RIGHT_MAX);
    writeSetting(STORAGE_KEY_RIGHT, String(rightWidth));
  }

  function setShowLeft(value: boolean) {
    showLeft = value;
    writeSetting(STORAGE_KEY_SHOW_LEFT, String(showLeft));
  }

  function setShowRight(value: boolean) {
    showRight = value;
    writeSetting(STORAGE_KEY_SHOW, String(showRight));
  }

  function setPromptHeight(height: number) {
    promptHeight = clamp(height, PROMPT_MIN, PROMPT_MAX);
    writeSetting(STORAGE_KEY_PROMPT, String(promptHeight));
  }

  // ── Drag handlers ─────────────────────────────────────────────────────────
  function onMouseMove(e: MouseEvent) {
    if (!dragging) return;

    if (dragging === "left") {
      setLeftWidth(dragStartSize + e.clientX - dragStartPosition);
    } else if (dragging === "right") {
      // Right sidebar grows leftward — delta is inverted
      setRightWidth(dragStartSize - (e.clientX - dragStartPosition));
    } else {
      // Prompt composer grows upward from the footer.
      setPromptHeight(dragStartSize - (e.clientY - dragStartPosition));
    }
  }

  function onMouseUp() {
    if (!dragging) return;
    dragging = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  }

  function startDrag(side: "left" | "right", e: MouseEvent) {
    e.preventDefault();
    dragging = side;
    dragStartPosition = e.clientX;
    dragStartSize = side === "left" ? leftWidth : rightWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  function startPromptDrag(e: MouseEvent) {
    e.preventDefault();
    dragging = "prompt";
    dragStartPosition = e.clientY;
    dragStartSize = promptHeight;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  // ── Public API ────────────────────────────────────────────────────────────
  return {
    get leftWidth() {
      return leftWidth;
    },
    get rightWidth() {
      return rightWidth;
    },
    get promptHeight() {
      return promptHeight;
    },
    get showLeft() {
      return showLeft;
    },
    set showLeft(v: boolean) {
      setShowLeft(v);
    },
    get showRight() {
      return showRight;
    },
    set showRight(v: boolean) {
      setShowRight(v);
    },

    startLeftDrag: (e: MouseEvent) => startDrag("left", e),
    startRightDrag: (e: MouseEvent) => startDrag("right", e),
    startPromptDrag,

    toggleLeft() {
      setShowLeft(!showLeft);
    },
    toggleRight() {
      setShowRight(!showRight);
    },

    resizeLeftBy(delta: number) {
      setLeftWidth(leftWidth + delta);
    },
    resizeRightBy(delta: number) {
      setRightWidth(rightWidth + delta);
    },
    resizePromptBy(delta: number) {
      setPromptHeight(promptHeight + delta);
    },

    resetLeft() {
      setLeftWidth(DEFAULT_LEFT);
    },
    resetRight() {
      setRightWidth(DEFAULT_RIGHT);
    },
    resetPrompt() {
      setPromptHeight(DEFAULT_PROMPT);
    },
  };
}
