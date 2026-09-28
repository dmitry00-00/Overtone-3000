import type { Ctx } from "../App";
import { Label, Section } from "../components/ui";
import { TEAM_LABEL, type RoundView, type Team } from "../types";
import { SummaryBlock } from "./SummaryScreen";

export function verdictLine(r: RoundView): string {
  const v = r.verdict;
  if (!v) return "без вердикта";
  if (v.is_aporia) {
    return { no_statements: "апория: выступлений не было", no_verdict: "апория: судья не вынес вердикт", judge_ruled_nobody: "не убедил никто — окно не двинулось", technical: "партия прервана" }[v.aporia_reason ?? ""] ?? "апория";
  }
  if (v.winner === null) return "исход определён вызовом";
  return `убедила ${TEAM_LABEL[v.winner]}` + (v.by_forfeit ? " — соперник не выступил" : "") + (v.move ? ` · ${v.move === "advance" ? "шаг себе" : "откат сопернику"}` : "");
}

export function RoundRecord({ r }: { r: RoundView }) {
  const teams: Team[] = ["team_a", "team_b"];
  return (
    <div className="stack">
      <div>
        <Label>Раунд {r.index} · {r.circumstance.code}</Label>
        <div className="h2">{r.circumstance.event}</div>
        <div className="meta">{verdictLine(r)}</div>
      </div>
      {teams.map((t) => (
        <div key={t}>
          <Label>{TEAM_LABEL[t]} · {r.hands[t].frame.title} · {r.hands[t].carrier.title}</Label>
          {r.statements[t] ? <div className="record">{r.statements[t]!.body}</div> : <div className="meta">выступление не сдано</div>}
          {r.challenges[t] && <div className="small muted">Вызов на №{r.challenges[t]!.claim_numbers.join(", ")}: {r.challenges[t]!.upheld === null ? "не рассмотрен" : r.challenges[t]!.upheld ? "засчитан" : "отклонён"}.</div>}
        </div>
      ))}
      <SummaryBlock r={r} />
    </div>
  );
}

export function HistoryScreen({ ctx }: { ctx: Ctx }) {
  const rounds = [...ctx.view.rounds].reverse();
  return (
    <>
      <Label>Прошлые раунды</Label>
      {rounds.map((r) => <Section key={r.index}><RoundRecord r={r} /></Section>)}
    </>
  );
}
