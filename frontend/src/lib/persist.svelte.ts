/**
 * lib/persist.ts
 * ===============
 * Thin localStorage wrapper for Svelte 5 runes.
 *
 * Usage:
 *   let count = persisted('my-app:count', 0);
 *   count.current;        // read
 *   count.current = 5;    // write (auto-persists)
 */

export function persisted<T>(key: string, fallback: T) {
  function load(): T {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? (JSON.parse(raw) as T) : fallback;
    } catch {
      return fallback;
    }
  }

  let value = $state<T>(load());

  return {
    get current(): T {
      return value;
    },
    set current(v: T) {
      value = v;
      localStorage.setItem(key, JSON.stringify(v));
    },
  };
}
