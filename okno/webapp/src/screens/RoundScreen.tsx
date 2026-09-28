import { useEffect, useState } from "react";
import { api } from "../api";
import type { Ctx } from "../App";
import { Button, CardBlock, ErrorLine, fmtDeadline, Label, Panel, Remaining, Section, useDraftGuard, wordCount } from "../components/ui";
import { MARK_LABEL, MARKS, other, TEAM_LABEL, type RoundView, type Team } from "../types";

const CHECKLIST = [
  "назвать опору — ценность, на которой держится ход",
  "усилить чужое — взять лучший довод соперника всерьёз",
  "найти уровень, на котором проект — частный случай принятой ценности",
  "выдержать реестр — не разойтись с прошлыми словами",
  "назвать условие, при котором вы откажетесь от меры",
];

export function Statement({ r, team, label }: { r: RoundView; team: Team; label: string }) {
  const s = r.statements[team];
  if (!s) return <Section><Label>{label}</Label><div className="muted small">{r.forfeits.includes(team) ? "выступление не сдано" : "ещё не раскрыто"}</div></Section>;
  return (
    <Section>
      <Label>{label}</Label>
      <div className="record">{s.body}</div>
    </Section>
  );
}

export function RoundScreen({ ctx }: { ctx: Ctx }) {
  const { view, act, error, go } = ctx;
  const r = view.round;
  const me = view.me.team;
  const id = view.game.id;
  const [text, setText] = useState("");
  const [claim, setClaim] = useState("");
  useEffect(() => {
    // Смена фазы или раунда: в STATEMENT поле держит сданный текст (правка до раскрытия),
    // в остальных фазах textarea начинается пустой — реплика не должна наследовать выступление.
    if (!r || !me) return;
    setText(r.phase === "statement" ? r.statements[me]?.body ?? "" : "");
  }, [r?.index, r?.phase]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (r && me) setClaim(r.claim_drafts[me] ?? ""); }, [r?.index, r?.phase]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = !!r && !!me && (
    (r.phase === "statement" && text.trim() !== "" && text.trim() !== (r.statements[me]?.body ?? "").trim()) ||
    (r.phase === "response" && !r.responses[me] && !r.challenges[me] && text.trim() !== "") ||
    (r.phase === "ledger" && claim.trim() !== "" && claim.trim() !== (r.claim_drafts[me] ?? "").trim())
  );
  useDraftGuard(dirty);

  if (!r) return <div className="muted">Раунд не идёт.</div>;
  const opp = me ? other(me) : null;
  const iAct = me ? r.pending.includes(me) : false;

  const head = (
    <Panel accent>
      <Label accent>Раунд {r.index} · {r.phase_title}</Label>
      <div className="h1">{view.prompt.text}</div>
      {r.deadline && <div className="muted small">Окно закрывается {fmtDeadline(r.deadline)}. <Remaining iso={r.deadline} /></div>}
    </Panel>
  );

  const cards = (
    <>
      <CardBlock label="Обстоятельство" code={r.circumstance.code} title={r.circumstance.event} note={r.circumstance.changes} />
      {me && (
        <>
          <CardBlock label="Ваш носитель" code={r.hands[me].carrier.code} title={r.hands[me].carrier.title} note={`Полезен: ${r.hands[me].carrier.benefit}. Опасен: ${r.hands[me].carrier.danger}.`} />
          <CardBlock label="Ваша рамка · говорить обязательно в ней" code={r.hands[me].frame.code} title={r.hands[me].frame.title} note={`Доказать: ${r.hands[me].frame.to_prove}. Ловушка: ${r.hands[me].frame.trap}.`} />
          {opp && <CardBlock label="Носитель и рамка соперника" title={`${r.hands[opp].carrier.title} · ${r.hands[opp].frame.title}`} />}
        </>
      )}
    </>
  );

  // ---------- наблюдатели: судья, журналист, выбывшие ----------
  if (!me) {
    return (
      <>
        {head}{cards}
        {(["team_a", "team_b"] as Team[]).map((t) => <Statement key={t} r={r} team={t} label={`Выступление · ${TEAM_LABEL[t]}`} />)}
        <ErrorLine error={error} />
      </>
    );
  }

  let body = null;
  switch (r.phase) {
    case "prep":
      body = (
        <Section>
          <p className="muted small">Обсудите ход с командой в своём чате. Когда готовы — отметьте: выступления откроются, как только готовы обе команды, или по дедлайну.</p>
          {r.ready.includes(me) ? <div className="meta">готовность отмечена · ждём соперника</div> : <Button primary onClick={() => act(() => api.ready(id))}>Мы готовы</Button>}
        </Section>
      );
      break;

    case "statement":
      body = (
        <>
          <Section>
            <Label>Выступление · {r.statements[me] ? "сдано, можно править до раскрытия" : "черновик"}</Label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Опора — ценность: ..." />
            <div className="row"><span className="meta">{text.length} знаков</span><span className="meta">соперник не видит до раскрытия</span></div>
          </Section>
          <Section>
            <Label>Из чего состоит выступление</Label>
            <ul className="checklist">{CHECKLIST.map((c, i) => <li key={i}><span className="n">{i + 1}</span><span>{c}</span></li>)}</ul>
            <div style={{ marginTop: 8 }}><button className="linkish" onClick={() => go("ledger")}>Ваши прошлые заявления · {view.ledger.filter((c) => c.team === me).length}</button></div>
          </Section>
          <Section>
            <Button primary disabled={!text.trim()} onClick={() => act(() => api.statement(id, text))}>{r.statements[me] ? "Сохранить правку" : "Отправить выступление"}</Button>
          </Section>
        </>
      );
      break;

    case "response":
      body = (
        <>
          {opp && <Statement r={r} team={opp} label={`Выступление соперника`} />}
          <Statement r={r} team={me} label="Ваше выступление" />
          {r.challenges[me] ? (
            <Section><Label>Вы заявили вызов</Label><div className="record">на заявления №{r.challenges[me]!.claim_numbers.join(", ")}: {r.challenges[me]!.argument}</div></Section>
          ) : r.responses[me] ? (
            <Section><Label>Ваша реплика сдана</Label><div className="record">{r.responses[me]!.body}</div></Section>
          ) : (
            <>
              <Section>
                <Label>Реплика</Label>
                <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Короткая реплика на выступление соперника" style={{ minHeight: 90 }} />
                <div style={{ marginTop: 8 }}><Button primary disabled={!text.trim()} onClick={() => act(() => api.response(id, text))}>Отправить реплику</Button></div>
              </Section>
              <Section>
                <Label>Или вместо реплики</Label>
                <p className="muted small">Вызов на противоречие: два заявления соперника из реестра и обоснование несовместимости. Засчитанный даёт шаг; отклонённый отдаёт ход сопернику.
                  {view.contradiction_hint !== null && view.contradiction_hint > 0 && ` В реестре соперника ${view.contradiction_hint} пары, требующие проверки.`}</p>
                <Button onClick={() => go("challenge")}>Заявить вызов</Button>
              </Section>
            </>
          )}
        </>
      );
      break;

    case "verdict":
      body = (
        <>
          {opp && <Statement r={r} team={opp} label="Выступление соперника" />}
          <Statement r={r} team={me} label="Ваше выступление" />
          <Section><div className="meta">судья читает</div></Section>
        </>
      );
      break;

    case "ledger": {
      const v = r.verdict!;
      const marks = r.marks[me];
      const needClaim = iAct && r.statements[me];
      const needMove = view.legal_moves.length > 0 && !r.move_choice;
      const wc = wordCount(claim);
      body = (
        <>
          <Section>
            <Label>Вердикт раунда</Label>
            <div className="h2">
              {v.is_aporia ? (v.aporia_reason === "no_verdict" ? "Судья не вынес вердикт — окно не двинулось" : "Не убедил никто — окно не двинулось")
                : v.winner === me ? "Судья: убедили вы" + (v.by_forfeit ? " — соперник не выступил" : "") : "Судья: убедил соперник" + (v.by_forfeit ? " — выступление не было сдано" : "")}
            </div>
            {marks && <div className="muted small">Судья отметил: {MARKS.filter((m) => marks[m]).map((m) => MARK_LABEL[m]).join(", ") || "—"}</div>}
            {Object.entries(r.challenges).map(([t, ch]) => (
              <div key={t} className="muted small">Вызов {t === me ? "ваш" : "соперника"}: {ch!.upheld === null ? "не рассмотрен" : ch!.upheld ? "засчитан" : "отклонён"}.</div>
            ))}
          </Section>
          {needMove && (
            <Section>
              <Label>Ход победителя</Label>
              <div className="btn-row">
                {view.legal_moves.includes("advance") && <Button primary onClick={() => act(() => api.move(id, "advance"))}>Шаг себе</Button>}
                {view.legal_moves.includes("push_back") && <Button onClick={() => act(() => api.move(id, "push_back"))}>Откат сопернику</Button>}
              </div>
            </Section>
          )}
          {r.move_choice && <Section><div className="meta">ход: {r.move_choice === "advance" ? "шаг себе" : "откат сопернику"}</div></Section>}
          {r.statements[me] && (
            <Section>
              <Label>Опорное заявление · до пятнадцати слов{r.claim_rejections[me] ? " · судья отклонил формулировку, напишите прямее" : ""}</Label>
              <textarea value={claim} onChange={(e) => setClaim(e.target.value)} style={{ minHeight: 64 }} placeholder="На чём стоит ваш ход — одной фразой" />
              <div className="row"><span className={"meta" + (wc > 15 ? " error" : "")}>{wc} / 15 слов</span>{r.claim_drafts[me] && <span className="meta">записано · можно переписать до закрытия</span>}</div>
              <div style={{ marginTop: 8 }}><Button primary disabled={!needClaim && !r.claim_drafts[me] || wc === 0 || wc > 15} onClick={() => act(() => api.claim(id, claim))}>Записать в реестр</Button></div>
            </Section>
          )}
        </>
      );
      break;
    }

    case "summary":
      body = <Section><div className="meta">журналист пишет сводку</div></Section>;
      break;
  }

  return (
    <>
      {head}
      {r.phase !== "statement" && cards}
      {r.phase === "statement" && me && (
        <Panel>
          <div className="row"><span className="label">Обстоятельство · {r.circumstance.code}</span></div>
          <div className="h2">{r.circumstance.event}</div>
          <div className="muted small">{r.circumstance.changes}</div>
          <div className="spacer" />
          <div className="row"><span className="label">Носитель · {r.hands[me].carrier.code}</span></div>
          <div className="h2">{r.hands[me].carrier.title}</div>
          <div className="muted small">{r.hands[me].carrier.benefit} — и {r.hands[me].carrier.danger}.</div>
          <div className="spacer" />
          <div className="row"><span className="label">Рамка · {r.hands[me].frame.code} · говорить обязательно в ней</span></div>
          <div className="h2">{r.hands[me].frame.title}</div>
          <div className="muted small">Доказать: {r.hands[me].frame.to_prove}. Ловушка: {r.hands[me].frame.trap}.</div>
        </Panel>
      )}
      {body}
      <ErrorLine error={error} />
    </>
  );
}
