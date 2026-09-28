import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, Label, Panel, Section } from "../components/ui";
import { openTgLink, tg } from "../tg";
import { ROLE_LABEL, TEAM_LABEL, type Role, type Team } from "../types";

export function Lobby({ ctx }: { ctx: Ctx }) {
  const { view, act, error, botUsername } = ctx;
  const id = view.game.id;
  const judging = view.game.judging;
  const mine = view.me.role;
  const humans = (t: Team) => view.players.filter((p) => p.team === t && p.active && !p.is_ai).length;
  const seated = (t: Team) => view.players.filter((p) => p.team === t && p.active).length;
  const hasJudge = view.players.some((p) => p.role === "judge" && p.active);

  const freeTeam: Role = humans("team_a") <= humans("team_b") ? "team_a" : "team_b";
  const [role, setRole] = useState<Role>(judging === "judge" ? "team_b" : freeTeam);
  const roles: Role[] = judging === "judge" ? ["team_a", "team_b", "judge", "journalist"] : ["team_a", "team_b"];

  const canStart =
    mine !== null && seated("team_a") > 0 && seated("team_b") > 0 && (judging !== "judge" || hasJudge);
  const startHint =
    judging === "judge" ? "нужны обе команды и судья"
    : judging === "mutual" ? "нужен соперник — пригласите друга"
    : "можно начинать";

  const invite = botUsername ? `https://t.me/${botUsername}?start=game_${id}` : `${location.origin}${location.pathname}?game=${id}`;
  const inviteText =
    judging === "mutual" ? "Сыграем в «Окно» один на один?" : judging === "self" ? "Идём со мной в одну команду в «Окне»?" : "Присоединяйся к партии в «Окне»";
  const share = () => openTgLink(`https://t.me/share/url?url=${encodeURIComponent(invite)}&text=${encodeURIComponent(inviteText)}`);

  const headline =
    judging === "self" ? "Соперник готов: это ИИ" : judging === "mutual" ? "Дуэль: пригласите соперника" : "Собираем состав";
  const note =
    judging === "self"
      ? "Вы судите обмены сами — честно, как в пасьянсе. Друг может войти в вашу команду. Партия тренировочная и в профиль не идёт."
      : judging === "mutual"
        ? "Судьи нет: после каждого обмена обе стороны выносят вердикт. Согласие двигает окно, несогласие — апория. В профиль не идёт."
        : "Старт — когда есть обе команды и судья. Журналист по желанию: без него сводку публикует ведущий.";

  return (
    <>
      <Panel accent>
        <Label accent>От вас сейчас</Label>
        <div className="h1">{mine ? headline : "Выберите роль и войдите"}</div>
        <div className="muted small">{note}</div>
      </Panel>

      <Section>
        <Label>Состав</Label>
        {view.players.map((p) => (
          <div key={p.id} className="row" style={{ padding: "6px 0" }}>
            <span>{p.display_name}{p.id === view.me.player_id ? " (вы)" : ""}</span>
            <span className="meta">{p.is_ai ? "ИИ · команда Б" : ROLE_LABEL[p.role]}</span>
          </div>
        ))}
      </Section>

      {!mine && (
        <Section>
          <div className="btn-row" style={{ marginBottom: 8 }}>
            {roles.map((r) => (
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
            <Label>Проект · {TEAM_LABEL[t]}{view.players.some((x) => x.team === t && x.is_ai) ? " (ИИ)" : ""} · {p.code}</Label>
            <div className="h2">{p.title}</div>
            <div className="muted small">старт {p.start} · известные возражения: {p.objections?.join("; ")}</div>
            {view.me.team === t && !p.swapped && (
              <div style={{ marginTop: 8 }}><Button onClick={() => act(() => api.swap(id))}>Сбросить и вытянуть заново (один раз)</Button></div>
            )}
            {p.swapped && <div className="meta">обмен использован</div>}
          </Section>
        );
      })}

      {mine && (
        <Section>
          <Label>{judging === "mutual" ? "Пригласить соперника" : judging === "self" ? "Позвать друга в команду" : "Позвать участников"}</Label>
          <div style={{ marginTop: 6 }}><Button onClick={share}>Пригласить в Telegram</Button></div>
          {!tg && <div className="record small" style={{ wordBreak: "break-all", marginTop: 6 }}>{invite}</div>}
        </Section>
      )}

      {mine && (
        <Section>
          <Button primary disabled={!canStart} onClick={() => act(() => api.start(id))}>Начать партию</Button>
          {!canStart && <div className="meta" style={{ marginTop: 6 }}>{startHint}</div>}
        </Section>
      )}
      <ErrorLine error={error} />
    </>
  );
}
