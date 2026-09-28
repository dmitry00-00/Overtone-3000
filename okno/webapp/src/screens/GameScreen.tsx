import type { Ctx, Screen } from "../App";
import { Button, CardBlock, ErrorLine, fmtDeadline, Label, Panel, Remaining, Section } from "../components/ui";
import { Track } from "../components/Track";
import { TEAM_LABEL, type Team } from "../types";

/** Куда ведёт главная кнопка и что на ней написано — по prompt.kind. */
function mainAction(kind: string, judging: string): { screen: Screen; text: string } | null {
  switch (kind) {
    case "prep": return { screen: "round", text: "Подготовка и готовность" };
    case "statement": return { screen: "round", text: "Написать выступление" };
    case "response": return { screen: "round", text: "Реплика или вызов" };
    case "ledger": return { screen: "round", text: "Записать опору" };
    case "move": return { screen: "round", text: "Выбрать ход" };
    case "verdict":
      return {
        screen: "judge",
        text: judging === "mutual" ? "Вынести взаимный вердикт" : judging === "self" ? "Судить обмен" : "Открыть карточку судьи",
      };
    case "summary": return { screen: "summary", text: "Написать сводку" };
    case "debrief": return { screen: "debrief", text: "Перейти к разбору" };
    default: return null;
  }
}

export function GameScreen({ ctx }: { ctx: Ctx }) {
  const { view, go, error } = ctx;
  const me = view.me.team;
  const r = view.round;
  const action = mainAction(view.prompt.kind, view.game.judging);
  const lastChanged = view.track.events.length ? view.track.events[view.track.events.length - 1] : null;
  const myProject = me ? view.projects[me] : null;
  const closed = view.rounds;
  const lastSummary = closed.length ? closed[closed.length - 1].summary : null;
  const aporia = view.game.status !== "in_progress" && view.game.outcome?.is_aporia;

  return (
    <>
      <Panel accent>
        <Label accent>От вас сейчас</Label>
        <div className="h1">{view.prompt.text}</div>
        {view.prompt.deadline && (
          <div className="muted small">Окно закрывается {fmtDeadline(view.prompt.deadline)}. <Remaining iso={view.prompt.deadline} /></div>
        )}
        {view.game.status === "debrief" && <div className="muted small">Партия не закрыта, пока каждый не оставит отметку.</div>}
        {aporia && <div className="muted small">Партия закончилась ничем. Разбор такой же подробный, как при победе.</div>}
      </Panel>

      {myProject && (
        <Panel>
          <Label>Ваш проект · {myProject.code}</Label>
          <div className="h2">{myProject.title}</div>
        </Panel>
      )}
      {!me && (
        <Panel>
          {(["team_a", "team_b"] as Team[]).map((t) => (
            <div key={t} className="row"><span className="label">{TEAM_LABEL[t]}</span><span className="small">{view.projects[t]?.title}</span></div>
          ))}
        </Panel>
      )}

      <Track view={view} changedRow={lastChanged && (lastChanged.team === me || !me) ? lastChanged.to : null} />

      {r && (
        <>
          <CardBlock label="Обстоятельство" code={r.circumstance.code} title={r.circumstance.event} note={r.circumstance.changes} />
          {me && (
            <>
              <CardBlock label="Ваш носитель" code={r.hands[me].carrier.code} title={r.hands[me].carrier.title} note={`${r.hands[me].carrier.benefit} — и ${r.hands[me].carrier.danger}.`} />
              <CardBlock label="Ваша рамка" code={r.hands[me].frame.code} title={r.hands[me].frame.title} note={`Доказать: ${r.hands[me].frame.to_prove}.`} />
            </>
          )}
          {r.audience && <CardBlock label="Публика раунда" code={r.audience.code} title={r.audience.mood} note={`Заходит: ${r.audience.accepts}. Отторгается: ${r.audience.rejects}.`} />}
        </>
      )}

      {action && <Section><Button primary onClick={() => go(action.screen)}>{action.text}</Button></Section>}
      {r && !action && view.me.role && <Section><Button onClick={() => go("round")}>Открыть раунд</Button></Section>}

      <Section>
        <div className="row">
          <button className="linkish" onClick={() => go("ledger")}>Реестр заявлений · {view.ledger.length}</button>
          {me && view.contradiction_hint !== null && view.contradiction_hint > 0 && (
            <span className="meta">у соперника {view.contradiction_hint} пары для проверки</span>
          )}
        </div>
      </Section>

      {lastSummary && (
        <Section>
          <Label>Сводка · раунд {closed[closed.length - 1].index}</Label>
          <div className="h2">{lastSummary.headline}</div>
          <div className="record muted">{lastSummary.body}</div>
        </Section>
      )}

      <Section>
        <div className="row">
          {closed.length > 0 && <button className="linkish" onClick={() => go("history")}>Прошлые раунды · {closed.length}</button>}
          {view.debrief && <button className="linkish" onClick={() => go("debrief")}>Разбор</button>}
        </div>
      </Section>
      <ErrorLine error={error} />
    </>
  );
}
