import { useRef, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, fmtDeadline, Label, Panel, Remaining, Section } from "../components/ui";
import { MARK_LABEL, MARKS, other, TEAM_LABEL, type MarkCode, type Team } from "../types";

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
  const judging = view.game.judging;
  const selfJudge = judging === "self" && view.me.team !== null;
  if (judging === "mutual" && view.me.team !== null) return <MutualVote ctx={ctx} />;
  if (!r || (view.me.role !== "judge" && !selfJudge)) return <div className="muted">Кабинет судьи.</div>;

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

  if (r.phase === "ledger" && selfJudge) {
    return <Panel><Label>Реестр</Label><div className="h2">{view.prompt.text}</div></Panel>;
  }
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
        <Label accent>{selfJudge ? "Самосуд" : "Кабинет судьи"} · раунд {r.index}</Label>
        {selfJudge && <div className="muted small">Тренировка: судите свой обмен так, как судила бы публика, — не как игрок.</div>}
        {r.audience && (
          <>
            <div className="h1">Публика: {r.audience.mood?.toLowerCase()}</div>
            <div className="muted small">Заходит: {r.audience.accepts}. Отторгается: {r.audience.rejects}. Судите так, как судила бы она.</div>
          </>
        )}
        {r.deadline && <div className="muted small">Окно закрывается {fmtDeadline(r.deadline)}. <Remaining iso={r.deadline} /></div>}
      </Panel>

      <div className="tabs">
        {teams.map((t) => <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{selfJudge ? (t === view.me.team ? "мы" : "соперник") : TEAM_LABEL[t]}{MARKS.some((m) => marks[t][m]) ? " ·" : ""}</button>)}
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
              <Button primary disabled={!r.statements.team_a} onClick={() => rule("team_a")}>{selfJudge ? (view.me.team === "team_a" ? "Убедили мы" : "Убедил соперник") : "Убедила А"}</Button>
              <Button primary disabled={!r.statements.team_b} onClick={() => rule("team_b")}>{selfJudge ? (view.me.team === "team_b" ? "Убедили мы" : "Убедил соперник") : "Убедила Б"}</Button>
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


/** Дуэль: взаимный вердикт. Отмечаешь карточку соперника и говоришь, кто убедил. */
function MutualVote({ ctx }: { ctx: Ctx }) {
  const { view, act, error, back } = ctx;
  const r = view.round;
  const id = view.game.id;
  const me = view.me.team!;
  const opp = other(me);
  const [marks, setMarks] = useState<MarkSet>(empty());
  const [winner, setWinner] = useState<Team | null | undefined>(undefined);
  const [concede, setConcede] = useState<boolean | undefined>(undefined);
  if (!r) return null;

  const myChallenge = r.challenges[me];
  const theirChallenge = r.challenges[opp]; // вызов, предъявленный нам
  const submitted = !!r.votes.mine;
  const anyChallenge = !!myChallenge || !!theirChallenge;
  const ready = submitted ? false : (anyChallenge || winner !== undefined) && (!theirChallenge || concede !== undefined);

  const submit = async () => {
    const payload = {
      winner: anyChallenge ? null : winner ?? null,
      opponent_marks: marks,
      challenge_concede: theirChallenge ? concede : null,
    };
    if (await act(() => api.vote(id, payload))) back();
  };

  if (r.phase !== "verdict") {
    return <Panel><Label>Взаимный вердикт</Label><div className="h2">{view.prompt.text}</div></Panel>;
  }

  return (
    <>
      <Panel accent>
        <Label accent>Взаимный вердикт · раунд {r.index}</Label>
        <div className="h1">Оцените обмен честно — соперник делает то же самое</div>
        <div className="muted small">Совпавший вердикт двигает окно. Несогласие — апория: не двигается никто.</div>
        {r.deadline && <div className="muted small">Окно закрывается {fmtDeadline(r.deadline)}. <Remaining iso={r.deadline} /></div>}
      </Panel>

      {r.audience && (
        <Section>
          <Label>Публика раунда · {r.audience.code}</Label>
          <div className="h2">{r.audience.mood}</div>
          <div className="muted small">Заходит: {r.audience.accepts}. Отторгается: {r.audience.rejects}. Судите так, как судила бы она.</div>
        </Section>
      )}

      <Section>
        <Label>Выступление соперника</Label>
        {r.statements[opp] ? <div className="record">{r.statements[opp]!.body}</div> : <div className="meta">не сдано</div>}
        {r.responses[opp] && <><div className="spacer" /><div className="record muted">Реплика: {r.responses[opp]!.body}</div></>}
      </Section>

      {submitted ? (
        <Section>
          <Label>Ваш голос сдан</Label>
          <div className="meta">{r.votes.opponent_submitted ? "сводим вердикты" : "ждём голос соперника"}</div>
        </Section>
      ) : (
        <>
          <Section>
            <Label>Отметки карточки соперника</Label>
            <ul className="marks">
              {MARKS.map((m) => (
                <li key={m} className={marks[m] ? "on" : ""} onClick={() => setMarks((s) => ({ ...s, [m]: !s[m] }))}>
                  <span className="box">{marks[m] ? "✓" : ""}</span><span>{MARK_LABEL[m]}</span>
                </li>
              ))}
            </ul>
          </Section>

          {theirChallenge && (
            <Section>
              <Label>Вам предъявлен вызов · заявления №{theirChallenge.claim_numbers.join(", №")}</Label>
              <div className="record">{theirChallenge.argument}</div>
              <div className="muted small" style={{ marginTop: 6 }}>Признание противоречия — достойный ход: оно и решает вызов.</div>
              <div className="btn-row" style={{ marginTop: 8 }}>
                <Button primary={concede === true} onClick={() => setConcede(true)}>Признать</Button>
                <Button primary={concede === false} onClick={() => setConcede(false)}>Отклонить</Button>
              </div>
            </Section>
          )}

          {!anyChallenge && (
            <Section>
              <Label>Кто убедил</Label>
              <div className="btn-row">
                <Button primary={winner === me} onClick={() => setWinner(me)}>Убедили мы</Button>
                <Button primary={winner === opp} onClick={() => setWinner(opp)}>Убедил соперник</Button>
              </div>
              <div style={{ marginTop: 8 }}>
                <Button primary={winner === null} onClick={() => setWinner(null)}>Не убедил никто — окно не двинулось</Button>
              </div>
            </Section>
          )}
          {myChallenge && <Section><div className="muted small">Вы заявили вызов: исход обмена решит ответ соперника на него.</div></Section>}

          <Section>
            <Button primary disabled={!ready} onClick={submit}>Сдать голос</Button>
          </Section>
        </>
      )}
      <ErrorLine error={error} />
    </>
  );
}
