import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, Label, Panel, Section } from "../components/ui";
import { other, TEAM_LABEL, type Claim, type Team } from "../types";
import { loadMarks, saveMarks } from "./ledgerState";

function ClaimRow({ c, suspect, selected, onTap, action }: { c: Claim; suspect?: boolean; selected?: boolean; onTap?: () => void; action?: React.ReactNode }) {
  const cls = "claim" + (c.retracted ? " retracted" : "") + (suspect ? " suspect" : "") + (selected ? " selected" : "") + (c.weak ? " weak" : "");
  return (
    <div className={cls} onClick={onTap} style={onTap ? { cursor: "pointer" } : undefined}>
      <div className="num">№{c.number} · раунд {c.round_index}</div>
      <div>{c.text}</div>
      {c.retracted && <div className="tag">отозвано в раунде {c.retracted_in_round}</div>}
      {c.challenged_in_round && <div className="tag">вызов засчитан в раунде {c.challenged_in_round}</div>}
      {action}
    </div>
  );
}

export function LedgerScreen({ ctx }: { ctx: Ctx }) {
  const { view, act, error, go } = ctx;
  const id = view.game.id;
  const me = view.me.team;
  const opp = me ? other(me) : null;
  const [marks, setMarks] = useState(() => loadMarks(id));
  const [retracting, setRetracting] = useState<number | null>(null);
  const update = (m: typeof marks) => { setMarks(m); saveMarks(id, m); };

  const left: Team = me ?? "team_a";
  const right: Team = opp ?? "team_b";
  const col = (t: Team) => view.ledger.filter((c) => c.team === t);
  const canRetract = view.game.status === "in_progress" && me !== null;
  const canChallenge = view.round?.phase === "response" && me !== null && !view.round.responses[me] && !view.round.challenges[me];

  const toggleSuspect = (n: number) => update({ ...marks, suspect: marks.suspect.includes(n) ? marks.suspect.filter((x) => x !== n) : [...marks.suspect, n] });
  const toggleSelect = (n: number) => {
    const sel = marks.selected.includes(n) ? marks.selected.filter((x) => x !== n) : [...marks.selected, n].slice(-2);
    update({ ...marks, selected: sel });
  };

  return (
    <>
      <Panel>
        <Label>Реестр заявлений · {view.ledger.length}</Label>
        <div className="muted small">Всё сказанное под записью. {opp ? "Нажатие на запись соперника выделяет её для вызова; «подозрительно» — пометка для себя, соперник её не видит." : ""}</div>
        {me && view.contradiction_hint !== null && view.contradiction_hint > 0 && <div className="muted small">В реестре соперника {view.contradiction_hint} пары заявлений, требующие проверки.</div>}
      </Panel>

      <div className="ledger">
        <div>
          <Label>{me ? "Вы" : TEAM_LABEL[left]}</Label>
          {col(left).map((c) => (
            <ClaimRow key={c.number} c={c} action={
              canRetract && !c.retracted && me === left ? (
                retracting === c.number ? (
                  <div style={{ marginTop: 6 }}>
                    <div className="muted small">Отзыв публичен и стоит шага назад на треке. Запись останется видимой с пометкой.</div>
                    <div className="btn-row" style={{ marginTop: 6 }}>
                      <Button onClick={async () => { if (await act(() => api.retract(id, c.number))) setRetracting(null); }}>Отозвать</Button>
                      <Button onClick={() => setRetracting(null)}>Оставить</Button>
                    </div>
                  </div>
                ) : <button className="linkish small" onClick={() => setRetracting(c.number)}>пересмотреть — отозвать</button>
              ) : null
            } />
          ))}
          {col(left).length === 0 && <div className="meta">пусто</div>}
        </div>
        <div>
          <Label>{me ? "Соперник" : TEAM_LABEL[right]}</Label>
          {col(right).map((c) => (
            <ClaimRow key={c.number} c={c}
              suspect={marks.suspect.includes(c.number)}
              selected={marks.selected.includes(c.number)}
              onTap={me && !c.retracted ? () => toggleSelect(c.number) : undefined}
              action={me && !c.retracted ? (
                <button className="linkish small" onClick={(e) => { e.stopPropagation(); toggleSuspect(c.number); }}>
                  {marks.suspect.includes(c.number) ? "снять пометку" : "подозрительно"}
                </button>
              ) : null}
            />
          ))}
          {col(right).length === 0 && <div className="meta">пусто</div>}
        </div>
      </div>

      {me && marks.selected.length === 2 && (
        <Section>
          <div className="muted small">Выбрана пара №{marks.selected.join(" и №")}.</div>
          <div style={{ marginTop: 8 }}>
            <Button primary={canChallenge} disabled={!canChallenge} onClick={() => go("challenge")}>
              {canChallenge ? "Заявить вызов на противоречие" : "Вызов заявляется в фазе реплики"}
            </Button>
          </div>
        </Section>
      )}
      <ErrorLine error={error} />
    </>
  );
}
