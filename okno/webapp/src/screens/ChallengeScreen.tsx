import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, Label, Panel, Section, useDraftGuard } from "../components/ui";
import { other } from "../types";
import { loadMarks, saveMarks } from "./ledgerState";

export function ChallengeScreen({ ctx }: { ctx: Ctx }) {
  const { view, act, error, back } = ctx;
  const id = view.game.id;
  const me = view.me.team;
  const [selected, setSelected] = useState<number[]>(() => loadMarks(id).selected);
  const [argument, setArgument] = useState("");
  useDraftGuard(argument.trim() !== "");
  if (!me) return <div className="muted">Вызов заявляет команда.</div>;
  const oppClaims = view.ledger.filter((c) => c.team === other(me) && !c.retracted);
  const canSubmit = view.round?.phase === "response" && !view.round.responses[me] && !view.round.challenges[me];
  const toggle = (n: number) => setSelected((s) => (s.includes(n) ? s.filter((x) => x !== n) : [...s, n].slice(-2)));

  const submit = async () => {
    if (await act(() => api.challenge(id, selected, argument))) { saveMarks(id, { ...loadMarks(id), selected: [] }); back(); }
  };

  return (
    <>
      <Panel accent>
        <Label accent>Вызов на противоречие</Label>
        <div className="h1">Два заявления соперника и почему они несовместимы</div>
        <div className="muted small">Вызов заменяет реплику. Засчитан — соперник откатывается на позицию, вы получаете шаг. Отклонён — вы теряете ход, соперник получает шаг бесплатно.</div>
      </Panel>

      <Section>
        <Label>Заявления соперника · выберите два</Label>
        {oppClaims.map((c) => (
          <div key={c.number} className={"claim" + (selected.includes(c.number) ? " selected" : "")} onClick={() => toggle(c.number)} style={{ cursor: "pointer" }}>
            <div className="num">№{c.number} · раунд {c.round_index}</div>
            <div>{c.text}</div>
          </div>
        ))}
        {oppClaims.length < 2 && <div className="meta">у соперника пока меньше двух заявлений</div>}
      </Section>

      <Section>
        <Label>Обоснование несовместимости</Label>
        <textarea value={argument} onChange={(e) => setArgument(e.target.value)} style={{ minHeight: 90 }} placeholder="В №2 утверждается…, что несовместимо с №5, где…" />
      </Section>

      <Section>
        <Button primary disabled={!canSubmit || selected.length !== 2 || !argument.trim()} onClick={submit}>
          {canSubmit ? "Заявить вызов вместо реплики" : "Вызов заявляется в фазе реплики"}
        </Button>
      </Section>
      <ErrorLine error={error} />
    </>
  );
}
