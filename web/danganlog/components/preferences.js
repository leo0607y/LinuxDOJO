const PREFS_KEY = 'dangan-log:prefs:v1';

export function readPrefs() {
  try { return JSON.parse(window.localStorage.getItem(PREFS_KEY) || '{}') || {}; } catch (e) { return {}; }
}
export function savePrefs(patch) {
  try { window.localStorage.setItem(PREFS_KEY, JSON.stringify(Object.assign(readPrefs(), patch))); } catch (e) { /* 保存できない環境 */ }
}
export function applyTheme(t) {
  const el = document.documentElement;
  if (t === 'dark' || t === 'light') el.setAttribute('data-theme', t); else el.removeAttribute('data-theme');
}
