import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, ErrorLine, Label, Panel, Section, useDraftGuard } from "../components/ui";
import { TEAM_LABEL, type RoundView, type Team } from "../types";

export function SummaryBlock({ r }: { r: RoundView }) {
  if (!r.summary) return null;
  return (
    <div className="print">
      <div className="label">Сводка · раунд {r.index} · {r.summary.author === "journalist" ? "журналист" : r.summary.author === "ai" ? "ведущий" : "система"}</div>
      <h3 className="headline">{r.summary.headline}</h3>
      <div className="lede">{r.summary.body}</div>
    </div>
  );
}

export function SummaryScreen({ ctx }: { ctx: Ctx }) {
  const { view, act, error, back } = ctx;
  const r = view.round;
  const id = view.game.id;
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  useDraftGuard(headline.trim() !== "" || body.trim() !== "");
  if (!r) return null;
  const teams: Team[] = ["team_a", "team_b"];
  const canWrite = view.me.role === "journalist" && r.phase === "summary" && !r.summary;

  return (
    <>
      <Panel accent>
        <Label accent>Сводка журналиста · раунд {r.index}</Label>
        <div className="h1">Что дошло до публики</div>
        <div className="muted small">Заголовок и три-четыре предложения. Только из сказанного командами: сокращать, смещать акцент, выносить в заголовок не главное — можно; приписывать слова — нет.</div>
      </Panel>

      {r.summary && <SummaryBlock r={r} />}

      {canWrite && (
        <>
          <Section>
            <Label>Заголовок</Label>
            <input type="text" value={headline} onChange={(e) => setHeadline(e.target.value)} placeholder="Что вынести первым" />
          </Section>
          <Section>
            <Label>Текст</Label>
            <textarea value={body} onChange={(e) => setBody(e.target.value)} style={{ minHeight: 110 }} />
          </Section>
          <Section>
            <Button primary disabled={!headline.trim() || !body.trim()} onClick={async () => { if (await act(() => api.summary(id, headline, body))) back(); }}>Опубликовать</Button>
          </Section>
        </>
      )}

      {teams.map((t) => r.statements[t] && (
        <Section key={t}>
          <Label>Оригинал · {TEAM_LABEL[t]}</Label>
          <div className="record">{r.statements[t]!.body}</div>
          {r.responses[t] && <div className="record muted" style={{ marginTop: 6 }}>Реплика: {r.responses[t]!.body}</div>}
        </Section>
      ))}
      <ErrorLine error={error} />
    </>
  );
}
