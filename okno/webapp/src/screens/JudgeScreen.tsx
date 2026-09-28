import { useRef, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, fmtDeadline, Label, Panel, Remaining, Section } from "../components/ui";
import { MARK_LABEL, MARKS, TEAM_LABEL, type MarkCode, type Team } from "../types";

type MarkSet = Record<MarkCode, boolean>;
const empty = (): MarkSet => ({ opora: false, steelman: false, level: false, ledger: false, condition: false });

/** Кабинет судьи. Обе карточки — за минуту: отметки ставятся по строке прямо при чтении. */
export function JudgeScreen({ ctx }: { ctx: Ctx }) {
  const { view, act, error, back } = ctx;
  const r = view.round;
  const id = view.game.id;
  const opened = useRef(Date.now());
  const [tab, setTab] = useState<Team>("team_a");
  const [marks, setMarks] = useState<Record<Team, MarkSet>>({ team_a: empty(), team_b: empty() });
  const [rulings, setRulings] = useState<Partial<Record<Team, boolean>>>({});
  if (!r || view.me.role !== "judge") return <div className="muted">Кабинет судьи.</div>;

  const teams: Team[] = ["team_a", "team_b"];
  const withStatement = teams.filter((t) => r.statements[t]);
  const challenges = Object.entries(r.challenges) as [Team, NonNullable<typeof r.challenges.team_a>][];
  const allRuled = challenges.every(([t]) => rulings[t] !== undefined);
  const toggle = (t: Team, m: MarkCode) => setMarks((s) => ({ ...s, [t]: { ...s[t], [m]: !s[t][m] } }));

  const rule = async (winner: Team | null) => {
    const payload = {
      winner: challenges.length ? null : winner,
      marks: Object.fromEntries(withStatement.map((t) => [t, marks[t]])),
      challenge_rulings: Object.fromEntries(challenges.map(([t]) => [t, rulings[t]])),
      fill_seconds: (Date.now() - opened.current) / 1000,
    };
    if (await act(() => api.rule(id, payload))) back();
  };

  const s = r.statements[tab];
  const resp = r.responses[tab];

  if (r.phase === "ledger") {
    return (
      <>
        <Panel><Label>Реестр · раунд {r.index}</Label><div className="h2">Команды пишут опоры</div><div className="muted small">Уклончивую формулировку можно отклонить — команда перепишет в том же окне.</div></Panel>
        {teams.map((t) => (
          <Section key={t}>
            <Label>{TEAM_LABEL[t]}</Label>
            {r.claim_drafts[t] ? (
              <>
                <div className="record">{r.claim_drafts[t]}</div>
                <div style={{ marginTop: 8 }}><Button onClick={() => act(() => api.rejectClaim(id, t))}>Отклонить как уклончивую</Button></div>
              </>
            ) : <div className="meta">{r.statements[t] ? "ещё не записано" : "команда не выступала"}</div>}
          </Section>
        ))}
        <ErrorLine error={error} />
      </>
    );
  }

  if (r.phase !== "verdict") {
    return <Panel><Label>Кабинет судьи</Label><div className="h2">{view.prompt.text}</div></Panel>;
  }

  return (
    <>
      <Panel accent>
        <Label accent>Кабинет судьи · раунд {r.index}</Label>
        {r.audience && (
          <>
            <div className="h1">Публика: {r.audience.mood?.toLowerCase()}</div>
            <div className="muted small">Заходит: {r.audience.accepts}. Отторгается: {r.audience.rejects}. Судите так, как судила бы она.</div>
          </>
        )}
        {r.deadline && <div className="muted small">Окно закрывается {fmtDeadline(r.deadline)}. <Remaining iso={r.deadline} /></div>}
      </Panel>

      <div className="tabs">
        {teams.map((t) => <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{TEAM_LABEL[t]}{MARKS.some((m) => marks[t][m]) ? " ·" : ""}</button>)}
      </div>

      <Section>
        <Label>Выступление · рамка {r.hands[tab].frame.title} · носитель {r.hands[tab].carrier.title}</Label>
        {s ? <div className="record">{s.body}</div> : <div className="meta">не сдано</div>}
        {resp && <><div className="spacer" /><Label>Реплика</Label><div className="record muted">{resp.body}</div></>}
      </Section>

      {s && (
        <Section>
          <Label>Структурные отметки · {TEAM_LABEL[tab]}</Label>
          <ul className="marks">
            {MARKS.map((m) => (
              <li key={m} className={marks[tab][m] ? "on" : ""} onClick={() => toggle(tab, m)}>
                <span className="box">{marks[tab][m] ? "✓" : ""}</span><span>{MARK_LABEL[m]}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {challenges.map(([t, ch]) => (
        <Section key={t}>
          <Label>Вызов от {TEAM_LABEL[t]} · заявления №{ch.claim_numbers.join(", №")}</Label>
          {ch.claim_numbers.map((n) => { const c = view.ledger.find((x) => x.team !== t && x.number === n); return c ? <div key={n} className="claim"><div className="num">№{c.number} · раунд {c.round_index}</div>{c.text}</div> : null; })}
          <div className="record" style={{ marginTop: 6 }}>{ch.argument}</div>
          <div className="btn-row" style={{ marginTop: 8 }}>
            <Button primary={rulings[t] === true} onClick={() => setRulings((x) => ({ ...x, [t]: true }))}>Засчитать</Button>
            <Button primary={rulings[t] === false} onClick={() => setRulings((x) => ({ ...x, [t]: false }))}>Отклонить</Button>
          </div>
        </Section>
      ))}

      <Section>
        <Label>Вердикт раунда</Label>
        {challenges.length > 0 && <div className="muted small">Заявлен вызов: исход обмена определяет решение по нему. Отметки всё равно нужны обеим командам.</div>}
        {challenges.length === 0 ? (
          <>
            <div className="btn-row">
              <Button primary disabled={!r.statements.team_a} onClick={() => rule("team_a")}>Убедила А</Button>
              <Button primary disabled={!r.statements.team_b} onClick={() => rule("team_b")}>Убедила Б</Button>
            </div>
            <div style={{ marginTop: 8 }}><Button onClick={() => rule(null)}>Не убедил никто — окно не двинулось</Button></div>
          </>
        ) : (
          <Button primary disabled={!allRuled} onClick={() => rule(null)}>Вынести вердикт по вызову</Button>
        )}
      </Section>
      <ErrorLine error={error} />
    </>
  );
}
