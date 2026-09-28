import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, Label, Panel, Section, useDraftGuard } from "../components/ui";
import { Track } from "../components/Track";
import { TEAM_LABEL, TRACK_LABELS, type Team } from "../types";
import { SummaryBlock } from "./SummaryScreen";

const ATOMS = ["назвать опору", "усилить чужое", "поднять уровень", "собрать в целое", "назвать условие", "пересмотреть под свидетельством", "сменить перспективу", "выдержать реестр"];

const CAUSE: Record<string, string> = {
  exchange_won: "выигранный обмен", pushed_back: "откат по ходу соперника", challenge_upheld: "засчитанный вызов", challenge_rejected: "отклонённый вызов соперника",
  retraction: "отзыв заявления", streak_progress: "первая из двух побед, нужных для выхода из «немыслимо»",
};

export function DebriefScreen({ ctx }: { ctx: Ctx }) {
  const { view, act, error } = ctx;
  const d = view.debrief;
  const id = view.game.id;
  const [worked, setWorked] = useState("");
  const [missed, setMissed] = useState("");
  useDraftGuard(worked.trim() !== "" || missed.trim() !== "");
  if (!d) return <div className="muted">Разбор ещё не открыт.</div>;
  const o = view.game.outcome;
  const me = view.me.player_id;
  const noted = d.notes_from.includes(me);
  const teams: Team[] = ["team_a", "team_b"];

  return (
    <>
      <Panel accent>
        <Label accent>Разбор</Label>
        <div className="h1">
          {o?.is_aporia ? "Партия закончилась ничем" : `Дальше провела проект ${TEAM_LABEL[o!.winner!]}`}
        </div>
        <div className="muted small">
          {teams.map((t) => `${TEAM_LABEL[t]}: ${o!.positions[t]} (${o!.deltas[t] >= 0 ? "+" : ""}${o!.deltas[t]} от старта)`).join(" · ")}
          {view.game.technical_aporia_from ? ` · прервана в раунде ${view.game.technical_aporia_from}` : ""}
        </div>
        <div className="muted small">{view.game.status === "completed" ? "Разбор завершён, партия засчитана." : view.game.status === "uncounted" ? "Разбор не завершён в срок, партия не засчитана." : `Ждём отметки: ${d.waiting_for.length}.`}</div>
      </Panel>

      <Section>
        <Label>1 · Проигрыш трека</Label>
        <Track view={view} />
        <div className="stack" style={{ marginTop: 12 }}>
          {d.track_replay.length === 0 && <div className="meta">фишки не двигались</div>}
          {d.track_replay.map((e, i) => (
            <div key={i}>
              <div className="meta">раунд {e.round_index} · {TEAM_LABEL[e.team]} · {e.from === e.to ? `${String(e.to).padStart(2, "0")} без сдвига` : `${String(e.from).padStart(2, "0")} → ${String(e.to).padStart(2, "0")} ${TRACK_LABELS[e.to]}`} · {CAUSE[e.cause] ?? e.cause}</div>
              {e.statement && e.cause !== "retraction" && <div className="record small muted">{e.cause === "pushed_back" || e.cause === "challenge_upheld" && e.from > e.to ? "" : "Вот этим ходом позиция стала приемлемее: "}{e.statement}</div>}
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <Label>2 · Реестр целиком</Label>
        {view.ledger.map((c) => (
          <div key={`${c.team}-${c.number}`} className={"claim" + (c.retracted ? " retracted" : "") + (c.weak ? " weak" : "")}>
            <div className="num">{TEAM_LABEL[c.team]} · №{c.number} · раунд {c.round_index}</div>
            <div>{c.text}</div>
            {c.retracted && <div className="tag">отозвано в раунде {c.retracted_in_round}</div>}
            {c.challenged_in_round && <div className="tag">вызов засчитан в раунде {c.challenged_in_round}</div>}
          </div>
        ))}
      </Section>

      <Section>
        <Label>3 · Сводки рядом с оригиналами</Label>
        <div className="muted small">Где журналист исказил, а где честно сжал? Второе важнее: если аргумент развалился при честном сжатии, проблема была в аргументе.</div>
        <div className="stack" style={{ marginTop: 10 }}>
          {view.rounds.filter((r) => r.summary || Object.keys(r.statements).length).map((r) => (
            <div key={r.index} className="stack">
              <SummaryBlock r={r} />
              {teams.map((t) => r.statements[t] && <div key={t}><Label>Оригинал · {TEAM_LABEL[t]} · раунд {r.index}</Label><div className="record small">{r.statements[t]!.body}</div></div>)}
            </div>
          ))}
        </div>
      </Section>

      <Section>
        <Label>4 · Личная отметка</Label>
        {noted ? (
          <div className="meta">ваша отметка записана</div>
        ) : view.game.status === "debrief" && view.players.some((p) => p.id === me && p.active) ? (
          <>
            <div className="muted small">Один сработавший атом и один пропущенный. Свободный текст; подсказка: {ATOMS.join(", ")}.</div>
            <div className="spacer" />
            <Label>Сработало</Label>
            <input type="text" value={worked} onChange={(e) => setWorked(e.target.value)} />
            <div className="spacer" />
            <Label>Пропущено</Label>
            <input type="text" value={missed} onChange={(e) => setMissed(e.target.value)} />
            <div className="spacer" />
            <Button primary disabled={!worked.trim() || !missed.trim()} onClick={() => act(() => api.debriefNote(id, worked, missed))}>Записать отметку</Button>
          </>
        ) : <div className="meta">отметки закрыты</div>}
      </Section>
      <ErrorLine error={error} />
    </>
  );
}
