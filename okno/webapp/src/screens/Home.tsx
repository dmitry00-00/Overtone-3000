import { useState } from "react";
import { api } from "../api";
import { Button, ErrorLine, Label, Panel, Section } from "../components/ui";
import { ROLE_LABEL, type GameView, type Me, type Role } from "../types";

const STATUS: Record<string, string> = { lobby: "лобби", in_progress: "идёт", debrief: "разбор", completed: "завершена", uncounted: "не засчитана" };

type Mode = "solo" | "duel" | "group";

const MODES: { mode: Mode; title: string; note: string }[] = [
  { mode: "solo", title: "Одиночная — против ИИ", note: "Вы ведёте проект против ИИ-соперника и сами судите обмены. Друг может присоединиться в вашу команду. Тренировка: в профиль не идёт." },
  { mode: "duel", title: "Дуэль с другом", note: "Двое, судьи нет: после обмена оба выносят вердикт; согласие двигает окно, несогласие — апория. Тренировка: в профиль не идёт." },
  { mode: "group", title: "Групповая", note: "Классика на 5–7 человек: две команды, судья, журналист. Только она отдаёт данные в профиль." },
];

export function Home({ me, onOpen, onCreated }: { me: Me | null; onOpen: (id: string) => void; onCreated: (v: GameView) => void }) {
  const [mode, setMode] = useState<Mode>("solo");
  const [role, setRole] = useState<Role>("team_a");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try { onCreated(await api.create(mode === "group" ? role : "team_a", mode)); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="page">
      <div className="topbar"><span className="brand">Окно</span><span className="meta">{me?.display_name ?? ""}</span></div>
      <Panel>
        <Label>Ваши партии</Label>
        {!me && <div className="muted small">загрузка</div>}
        {me && me.games.length === 0 && <div className="muted small">Партий пока нет.</div>}
        {me?.games.map((g) => (
          <div key={g.id} className="section">
            <button className="linkish" onClick={() => onOpen(g.id)}>партия {g.id.slice(0, 6)}</button>
            <div className="meta">{STATUS[g.status] ?? g.status}{g.round_index ? ` · раунд ${g.round_index}` : ""} · {ROLE_LABEL[g.role]}</div>
          </div>
        ))}
      </Panel>
      <Section>
        <Label>Новая партия</Label>
        {MODES.map((m) => (
          <div key={m.mode} className={"claim" + (mode === m.mode ? " selected" : "")} onClick={() => setMode(m.mode)} style={{ cursor: "pointer" }}>
            <div className="h2" style={{ fontFamily: "var(--sans)" }}>{m.title}</div>
            <div className="muted small" style={{ fontFamily: "var(--sans)" }}>{m.note}</div>
          </div>
        ))}
        {mode === "group" && (
          <div className="btn-row" style={{ margin: "10px 0 2px" }}>
            {(["team_a", "team_b", "judge", "journalist"] as Role[]).map((r) => (
              <button key={r} className={"btn" + (role === r ? " primary" : "")} onClick={() => setRole(r)}>{ROLE_LABEL[r]}</button>
            ))}
          </div>
        )}
        <div style={{ marginTop: 10 }}>
          <Button primary onClick={create} disabled={busy}>Создать партию</Button>
        </div>
        <ErrorLine error={error} />
      </Section>
    </div>
  );
}
