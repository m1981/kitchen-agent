/**
 * lib/types/states.ts
 * ====================
 * Generic typed state machine for async operations.
 *
 * Eliminates the "boolean soup" anti-pattern where separate `isLoading`,
 * `error`, `data` flags can co-exist in impossible combinations (e.g.
 * loading=true AND error set simultaneously).
 *
 * Usage:
 *   let state = $state<AsyncState<string[]>>({ status: 'idle' });
 *   state = { status: 'loading' };
 *   state = { status: 'success', data: ['a', 'b'] };
 *   state = { status: 'error', message: 'Network error' };
 *
 *   // Exhaustive switch — TypeScript will complain if you miss a branch.
 *   switch (state.status) {
 *     case 'idle':    return 'Nothing yet';
 *     case 'loading': return 'Thinking…';
 *     case 'success': return state.data.join(', ');
 *     case 'error':   return `Error: ${state.message}`;
 *   }
 */
export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: T };
