import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { startGameId, tg } from "./tg";
import type { GameView, Me } from "./types";
import { Home } from "./screens/Home";
import { Lobby } from "./screens/Lobby";
import { GameScreen } from "./screens/GameScreen";
import { RoundScreen } from "./screens/RoundScreen";
import { LedgerScreen } from "./screens/LedgerScreen";
import { ChallengeScreen } from "./screens/ChallengeScreen";
import { JudgeScreen } from "./screens/JudgeScreen";
import { SummaryScreen } from "./screens/SummaryScreen";
import { DebriefScreen } from "./screens/DebriefScreen";
import { HistoryScreen } from "./screens/HistoryScreen";

export type Screen = "home" | "game" | "round" | "ledger" | "challenge" | "judge" | "summary" | "debrief" | "history";

export interface Ctx {
  view: GameView;
  botUsername: string | null;
  refresh: () => Promise<void>;
  /** Выполнить действие; ответ сервера становится новым состоянием. */
  act: (fn: () => Promise<GameView>) => Promise<boolean>;
  error: string | null;
  go: (s: Screen) => void;
  back: () => void;
}

const POLL_MS = 15_000;

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [gameId, setGameId] = useState<string | null>(startGameId());
  const [view, setView] = useState<GameView | null>(null);
  const [stack, setStack] = useState<Screen[]>(gameId ? ["home", "game"] : ["home"]);
  const [error, setError] = useState<string | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const screen = stack[stack.length - 1];
  const viewRef = useRef(view);
  viewRef.current = view;

  const loadMe = useCallback(async () => {
    try { setMe(await api.me()); } catch (e) { setFatal(e instanceof Error ? e.message : String(e)); }
  }, []);

  const refresh = useCallback(async () => {
    if (!gameId) return;
    try { setView(await api.game(gameId)); setError(null); }
    catch (e) { if (e instanceof ApiError && e.status === 404) { setGameId(null); setStack(["home"]); } else setError(e instanceof Error ? e.message : String(e)); }
  }, [gameId]);

  useEffect(() => { loadMe(); }, [loadMe]);
  useEffect(() => { setView(null); refresh(); }, [refresh]);
  useEffect(() => {
    const t = setInterval(() => { if (document.visibilityState === "visible") refresh(); }, POLL_MS);
    const onVis = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh]);

  const go = useCallback((s: Screen) => setStack((st) => [...st, s]), []);
  const back = useCallback(() => setStack((st) => (st.length > 1 ? st.slice(0, -1) : st)), []);

  useEffect(() => {
    const t = tg;
    if (!t) return;
    if (stack.length > 1) { t.BackButton.show(); t.BackButton.onClick(back); } else t.BackButton.hide();
    return () => t.BackButton.offClick(back);
  }, [stack, back]);

  const act = useCallback(async (fn: () => Promise<GameView>) => {
    try { setView(await fn()); setError(null); tg?.HapticFeedback?.impactOccurred("light"); return true; }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); return false; }
  }, []);

  const openGame = (id: string) => { setGameId(id); setStack(["home", "game"]); };

  if (fatal) {
    return (
      <div className="page">
        <div className="topbar"><span className="brand">Окно</span></div>
        <div className="error">{fatal}</div>
        <p className="muted small">Откройте приложение из Telegram. Для локальной разработки добавьте к адресу <span className="record">?dev=a1:Аня</span> и запустите сервер с OKNO_DEV_AUTH=1.</p>
      </div>
    );
  }

  if (screen === "home" || !gameId) {
    return <Home me={me} onOpen={openGame} onCreated={(v) => { setView(v); openGame(v.game.id); loadMe(); }} />;
  }
  if (!view) return <div className="page"><div className="topbar"><span className="brand">Окно</span><span className="meta">загрузка</span></div></div>;

  const ctx: Ctx = { view, botUsername: me?.bot_username ?? null, refresh, act, error, go, back };
  const header = (
    <div className="topbar">
      <span className="brand">Окно</span>
      <span className="meta">партия {view.game.id.slice(0, 6)}{view.round ? ` · раунд ${view.round.index}/${view.game.rounds_total}` : ""}</span>
    </div>
  );

  let body;
  if (view.game.status === "lobby") body = <Lobby ctx={ctx} />;
  else switch (screen) {
    case "round": body = <RoundScreen ctx={ctx} />; break;
    case "ledger": body = <LedgerScreen ctx={ctx} />; break;
    case "challenge": body = <ChallengeScreen ctx={ctx} />; break;
    case "judge": body = <JudgeScreen ctx={ctx} />; break;
    case "summary": body = <SummaryScreen ctx={ctx} />; break;
    case "debrief": body = <DebriefScreen ctx={ctx} />; break;
    case "history": body = <HistoryScreen ctx={ctx} />; break;
    default: body = <GameScreen ctx={ctx} />;
  }
  return (
    <div className="page">
      {header}
      {!tg && stack.length > 1 && <button className="linkish" onClick={back}>← назад</button>}
      {!tg && stack.length === 1 && <button className="linkish" onClick={() => { setGameId(null); setStack(["home"]); loadMe(); }}>← партии</button>}
      {body}
    </div>
  );
}
