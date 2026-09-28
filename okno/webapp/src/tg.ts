// Связь с Telegram WebApp: авторизация, тема, кнопка «назад». Вне Telegram — dev-режим.

interface TgWebApp {
  initData: string;
  initDataUnsafe: { start_param?: string };
  colorScheme: "light" | "dark";
  ready(): void;
  expand(): void;
  onEvent(e: string, cb: () => void): void;
  offEvent(e: string, cb: () => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: { impactOccurred(style: string): void };
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  enableClosingConfirmation?(): void;
  disableClosingConfirmation?(): void;
  disableVerticalSwipes?(): void;
}

declare global { interface Window { Telegram?: { WebApp: TgWebApp } } }

export const tg: TgWebApp | null = window.Telegram?.WebApp && window.Telegram.WebApp.initData ? window.Telegram.WebApp : null;

const params = new URLSearchParams(location.search);

/** dev-пользователь: ?dev=a1:Аня в адресе или из localStorage. */
export function devUser(): string | null {
  const q = params.get("dev");
  if (q) { try { localStorage.setItem("okno.dev", q); } catch { /* приватный режим */ } return q; }
  try { return localStorage.getItem("okno.dev"); } catch { return null; }
}

export function authHeaders(): Record<string, string> {
  if (tg) return { Authorization: `tma ${tg.initData}` };
  const d = devUser();
  if (d) { const [id, name] = d.split(":"); return { "X-Dev-User": name ? `${id}:${encodeURIComponent(name)}` : id }; }
  return {};
}

/** Партия из deep-link: ?game=<id> или start_param Mini App. */
export function startGameId(): string | null {
  return params.get("game") || tg?.initDataUnsafe.start_param || null;
}

export function applyTheme(): void {
  const scheme = tg?.colorScheme ?? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.dataset.theme = scheme;
  // Шапка и фон Telegram красятся в лист протокола, чтобы приложение не выглядело вставкой.
  const bg = scheme === "light" ? "#f3f1ec" : "#0f0f0f";
  try { tg?.setHeaderColor?.(bg); tg?.setBackgroundColor?.(bg); } catch { /* старый клиент */ }
}

/** Несохранённый черновик: Telegram спрашивает подтверждение перед закрытием Mini App. */
export function guardDraft(active: boolean): void {
  try { active ? tg?.enableClosingConfirmation?.() : tg?.disableClosingConfirmation?.(); } catch { /* старый клиент */ }
}

export function initTelegram(): void {
  applyTheme();
  if (!tg) return;
  tg.ready();
  tg.expand();
  try { tg.disableVerticalSwipes?.(); } catch { /* до Bot API 7.7 */ }
  tg.onEvent("themeChanged", applyTheme);
}
