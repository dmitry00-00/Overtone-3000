// Зеркало okno/api/views.py.

export type Team = "team_a" | "team_b";
export type Role = "team_a" | "team_b" | "judge" | "journalist";
export type Phase = "opening" | "prep" | "statement" | "reveal" | "response" | "verdict" | "ledger" | "summary" | "closed";
export type MarkCode = "opora" | "steelman" | "level" | "ledger" | "condition";

export interface Card { code: string; title?: string; [k: string]: unknown }
export interface Circumstance extends Card { event?: string; changes?: string }
export interface Audience extends Card { mood?: string; accepts?: string; rejects?: string }
export interface Carrier extends Card { benefit?: string; danger?: string }
export interface Frame extends Card { to_prove?: string; trap?: string }
export interface Project extends Card { start?: number; objections?: [string, string]; swapped?: boolean }

export interface Prompt { kind: string; text: string; deadline: string | null }

export interface RoundView {
  index: number;
  phase: Phase;
  phase_title: string;
  phase_started_at: string | null;
  deadline: string | null;
  opened_at: string | null;
  circumstance: Circumstance;
  audience: Audience | null;
  hands: Record<Team, { carrier: Carrier; frame: Frame }>;
  ready: Team[];
  forfeits: Team[];
  statements: Partial<Record<Team, { body: string; submitted_at: string; author_id: string; edit_count: number }>>;
  responses: Partial<Record<Team, { body: string; submitted_at: string }>>;
  challenges: Partial<Record<Team, { claim_numbers: number[]; argument: string; upheld: boolean | null; ruled_at: string | null }>>;
  verdict: { winner: Team | null; is_aporia: boolean; aporia_reason: string | null; by_forfeit: boolean; move: string | null; ruled_at: string } | null;
  marks: Partial<Record<Team, Record<MarkCode, boolean>>>;
  claim_drafts: Partial<Record<Team, string>>;
  claim_rejections: Partial<Record<Team, number>>;
  move_choice: string | null;
  summary: { headline: string; body: string; author: string; published_at: string } | null;
  pending: string[];
  transitions: { from: Phase; to: Phase; at: string; by_timeout: boolean }[];
}

export interface Claim {
  team: Team; number: number; round_index: number; text: string; weak: boolean;
  retracted: boolean; retracted_in_round: number | null; challenged_in_round: number | null;
}

export interface TrackEvent { round_index: number; team: Team; from: number; to: number; cause: string; at: string }

export interface GameView {
  prompt: Prompt;
  game: {
    id: string; status: "lobby" | "in_progress" | "debrief" | "completed" | "uncounted";
    created_at: string | null; rounds_total: number; rounds_played: number; technical_aporia_from: number | null;
    outcome: { winner: Team | null; is_aporia: boolean; aporia_reason: string | null; positions: Record<Team, number>; deltas: Record<Team, number> } | null;
  };
  me: { player_id: string; role: Role | null; team: Team | null; display_name: string | null };
  players: { id: string; display_name: string; role: Role; team: Team | null; active: boolean }[];
  projects: Partial<Record<Team, Project>>;
  track: { size: number; positions: Record<Team, number>; start: Record<Team, number>; streak: Record<Team, number>; events: TrackEvent[] };
  round: RoundView | null;
  rounds: RoundView[];
  ledger: Claim[];
  contradiction_hint: number | null;
  legal_moves: string[];
  structural_mine: { round_index: number; atom: string; at: string }[];
  debrief: {
    started_at: string; deadline: string; completed_at: string | null; notes_from: string[]; waiting_for: string[];
    track_replay: { round_index: number; team: Team; from: number; to: number; cause: string; statement: string | null }[];
    export_allowed: boolean;
  } | null;
}

export interface Me { player_id: string; display_name: string; games: { id: string; status: string; role: Role; updated_at: string; round_index: number | null; phase: Phase | null }[] }

export const TRACK_LABELS = ["немыслимо", "радикально", "приемлемо", "разумно", "популярно", "норма"];
export const TEAM_LABEL: Record<Team, string> = { team_a: "команда А", team_b: "команда Б" };
export const ROLE_LABEL: Record<Role, string> = { team_a: "команда А", team_b: "команда Б", judge: "судья", journalist: "журналист" };
export const MARK_LABEL: Record<MarkCode, string> = {
  opora: "назвал опору", steelman: "усилил чужое", level: "нашёл уровень", ledger: "выдержал реестр", condition: "назвал условие",
};
export const MARKS: MarkCode[] = ["opora", "steelman", "level", "ledger", "condition"];
export const other = (t: Team): Team => (t === "team_a" ? "team_b" : "team_a");
