import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, Label, Panel, Section } from "../components/ui";
import { ROLE_LABEL, TEAM_LABEL, type Role, type Team } from "../types";

export function Lobby({ ctx }: { ctx: Ctx }) {
  const { view, act, error } = ctx;
  const id = view.game.id;
  const [role, setRole] = useState<Role>("team_b");
  const mine = view.me.role;
  const teamA = view.players.filter((p) => p.team === "team_a").length;
  const teamB = view.players.filter((p) => p.team === "team_b").length;
  const hasJudge = view.players.some((p) => p.role === "judge");
  const canStart = mine !== null && teamA > 0 && teamB > 0 && hasJudge;
  const link = `${location.origin}${location.pathname}?game=${id}`;

  return (
    <>
      <Panel accent>
        <Label accent>От вас сейчас</Label>
        <div className="h1">{mine ? "Собираем состав" : "Выберите роль и войдите"}</div>
        <div className="muted small">Старт — когда есть обе команды и судья. Журналист по желанию: без него сводку публикует ведущий.</div>
      </Panel>

      <Section>
        <Label>Состав</Label>
        {view.players.map((p) => (
          <div key={p.id} className="row" style={{ padding: "6px 0" }}>
            <span>{p.display_name}{p.id === view.me.player_id ? " (вы)" : ""}</span>
            <span className="meta">{ROLE_LABEL[p.role]}</span>
          </div>
        ))}
      </Section>

      {!mine && (
        <Section>
          <div className="btn-row" style={{ marginBottom: 8 }}>
            {(["team_a", "team_b", "judge", "journalist"] as Role[]).map((r) => (
              <button key={r} className={"btn" + (role === r ? " primary" : "")} onClick={() => setRole(r)}>{ROLE_LABEL[r]}</button>
            ))}
          </div>
          <Button primary onClick={() => act(() => api.join(id, role))}>Войти в партию</Button>
        </Section>
      )}

      {(["team_a", "team_b"] as Team[]).map((t) => {
        const p = view.projects[t];
        if (!p) return null;
        return (
          <Section key={t}>
            <Label>Проект · {TEAM_LABEL[t]} · {p.code}</Label>
            <div className="h2">{p.title}</div>
            <div className="muted small">старт {p.start} · известные возражения: {p.objections?.join("; ")}</div>
            {view.me.team === t && !p.swapped && (
              <div style={{ marginTop: 8 }}><Button onClick={() => act(() => api.swap(id))}>Сбросить и вытянуть заново (один раз)</Button></div>
            )}
            {p.swapped && <div className="meta">обмен использован</div>}
          </Section>
        );
      })}

      <Section>
        <Label>Ссылка для остальных</Label>
        <div className="record" style={{ wordBreak: "break-all" }}>{link}</div>
      </Section>

      {mine && (
        <Section>
          <Button primary disabled={!canStart} onClick={() => act(() => api.start(id))}>Начать партию</Button>
          {!canStart && <div className="meta" style={{ marginTop: 6 }}>нужны обе команды и судья</div>}
        </Section>
      )}
      <ErrorLine error={error} />
    </>
  );
}
