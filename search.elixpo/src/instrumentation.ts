// Node.js v25+ exposes a broken `localStorage` global (object exists but
// getItem/setItem are undefined).  This crashes any code — including Next.js
// internals and third-party libs — that feature-detects `localStorage` and
// then calls its methods.
//
// This instrumentation file runs once at server startup and replaces the
// broken global with a silent no-op implementation so SSR never crashes.

export async function register() {
  if (typeof window === 'undefined') {
    const noop = () => null;
    const noopStorage = {
      getItem: noop,
      setItem: noop,
      removeItem: noop,
      clear: noop,
      key: noop,
      length: 0,
    };
    (globalThis as any).localStorage = noopStorage;
    (globalThis as any).sessionStorage = noopStorage;
  }
}
