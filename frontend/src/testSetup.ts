import '@testing-library/jest-dom';

// Vitest 4 + jsdom does not expose localStorage.clear() reliably.
// Replace with a fully functional in-memory implementation for all tests.
const _localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string): string | null => store[key] ?? null,
    setItem: (key: string, value: string): void => { store[key] = String(value); },
    removeItem: (key: string): void => { delete store[key]; },
    clear: (): void => { store = {}; },
    get length(): number { return Object.keys(store).length; },
    key: (i: number): string | null => Object.keys(store)[i] ?? null,
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: _localStorageMock,
  writable: true,
});
