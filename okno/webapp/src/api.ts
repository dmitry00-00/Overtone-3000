import { authHeaders } from "./tg";
import type { GameView, Me } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* не json */ }
    throw new ApiError(r.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json();
}

export const api = {
  me: () => call<Me>("GET", "/api/me"),
  game: (id: string) => call<GameView>("GET", `/api/games/${id}`),
  create: (role: string, mode: string = "group", rounds?: number, round_hours?: number) => call<GameView>("POST", "/api/games", { role, mode, rounds, round_hours }),
  join: (id: string, role: string) => call<GameView>("POST", `/api/games/${id}/join`, { role }),
  start: (id: string) => call<GameView>("POST", `/api/games/${id}/start`),
  swap: (id: string) => call<GameView>("POST", `/api/games/${id}/swap-project`),
  ready: (id: string) => call<GameView>("POST", `/api/games/${id}/ready`),
  statement: (id: string, body: string) => call<GameView>("POST", `/api/games/${id}/statement`, { body }),
  response: (id: string, body: string) => call<GameView>("POST", `/api/games/${id}/response`, { body }),
  challenge: (id: string, claim_numbers: number[], argument: string) => call<GameView>("POST", `/api/games/${id}/challenge`, { claim_numbers, argument }),
  claim: (id: string, body: string) => call<GameView>("POST", `/api/games/${id}/claim`, { body }),
  move: (id: string, move: string) => call<GameView>("POST", `/api/games/${id}/move`, { move }),
  retract: (id: string, number: number) => call<GameView>("POST", `/api/games/${id}/retract`, { number }),
  rule: (id: string, payload: unknown) => call<GameView>("POST", `/api/games/${id}/rule`, payload),
  vote: (id: string, payload: unknown) => call<GameView>("POST", `/api/games/${id}/vote`, payload),
  rejectClaim: (id: string, team: string) => call<GameView>("POST", `/api/games/${id}/reject-claim`, { team }),
  summary: (id: string, headline: string, body: string) => call<GameView>("POST", `/api/games/${id}/summary`, { headline, body }),
  debriefNote: (id: string, atom_worked: string, atom_missed: string) => call<GameView>("POST", `/api/games/${id}/debrief-note`, { atom_worked, atom_missed }),
  leave: (id: string) => call<GameView>("POST", `/api/games/${id}/leave`),
};
