import { TRACK_LABELS, type GameView, type Team } from "../types";

/** Трек окна: шесть делений снизу вверх. Слева вы, справа соперник; формой, не цветом. */
export function Track({ view, changedRow }: { view: GameView; changedRow?: number | null }) {
  const me: Team = view.me.team ?? "team_a";
  const opp: Team = me === "team_a" ? "team_b" : "team_a";
  const t = view.track;
  const rows = [];
  for (let pos = t.size - 1; pos >= 0; pos--) {
    const mine = t.positions[me] === pos;
    const theirs = t.positions[opp] === pos;
    const startMine = t.start[me] === pos && !mine;
    const startTheirs = t.start[opp] === pos && !theirs;
    rows.push(
      <div key={pos} className={"track-row" + (changedRow === pos ? " changed" : "")}>
        <span className="num">{String(pos).padStart(2, "0")}</span>
        <span className={"name" + (mine ? " current" : "")}>{TRACK_LABELS[pos]}</span>
        <span>{mine ? <span className="mark me" /> : startMine ? <span className="mark start" /> : null}</span>
        <span>{theirs ? <span className="mark opp" /> : startTheirs ? <span className="mark start" /> : null}</span>
      </div>,
    );
  }
  return (
    <div>
      <div className="row">
        <span className="label">Трек окна</span>
        <span className="meta">{view.me.team ? "вы" : "А"} {t.positions[me]} · {view.me.team ? "соперник" : "Б"} {t.positions[opp]}</span>
      </div>
      <div className="spacer" style={{ height: 6 }} />
      <div className="track">{rows}</div>
      <div className="legend">
        <span><span className="mark me" />{view.me.team ? "вы" : "команда А"}</span>
        <span><span className="mark opp" />{view.me.team ? "соперник" : "команда Б"}</span>
        <span><span className="mark start" />старт</span>
      </div>
    </div>
  );
}
