import { useState } from "react";
import { api } from "../api";
import { Button, ErrorLine, Label, Panel, Section } from "../components/ui";
import { ROLE_LABEL, type GameView, type Me, type Role } from "../types";

const STATUS: Record<string, string> = { lobby: "лобби", in_progress: "идёт", debrief: "разбор", completed: "завершена", uncounted: "не засчитана" };

export function Home({ me, onOpen, onCreated }: { me: Me | null; onOpen: (id: string) => void; onCreated: (v: GameView) => void }) {
  const [role, setRole] = useState<Role>("team_a");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try { onCreated(await api.create(role)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
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
        <p className="muted small">Обычно партию создаёт бот командой /new в групповом чате. Здесь — то же самое без чата: создайте и передайте остальным ссылку.</p>
        <div className="btn-row" style={{ marginBottom: 8 }}>
          {(["team_a", "team_b", "judge", "journalist"] as Role[]).map((r) => (
            <button key={r} className={"btn" + (role === r ? " primary" : "")} onClick={() => setRole(r)}>{ROLE_LABEL[r]}</button>
          ))}
        </div>
        <Button primary onClick={create} disabled={busy}>Создать партию</Button>
        <ErrorLine error={error} />
      </Section>
    </div>
  );
}
