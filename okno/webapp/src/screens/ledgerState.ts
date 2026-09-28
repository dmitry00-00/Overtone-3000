// Рабочие пометки реестра — «подозрительное» и выбранная пара. Личное, живёт в браузере.

export interface LedgerMarks { suspect: number[]; selected: number[] }

const key = (gameId: string) => `okno.ledger.${gameId}`;

export function loadMarks(gameId: string): LedgerMarks {
  try { const raw = localStorage.getItem(key(gameId)); if (raw) return JSON.parse(raw); } catch { /* нет хранилища */ }
  return { suspect: [], selected: [] };
}

export function saveMarks(gameId: string, m: LedgerMarks): void {
  try { localStorage.setItem(key(gameId), JSON.stringify(m)); } catch { /* нет хранилища */ }
}
