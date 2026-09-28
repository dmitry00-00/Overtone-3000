import { useEffect, useState, type ReactNode } from "react";
import { guardDraft } from "../tg";

export function Label({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <div className={"label" + (accent ? " accent" : "")}>{children}</div>;
}

export function Panel({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <div className={"panel" + (accent ? " accent-rule" : "")}>{children}</div>;
}

export function Section({ children }: { children: ReactNode }) {
  return <div className="section">{children}</div>;
}

export function Button({ children, primary, onClick, disabled, inline }: { children: ReactNode; primary?: boolean; onClick?: () => void; disabled?: boolean; inline?: boolean }) {
  return (
    <button className={"btn" + (primary ? " primary" : "") + (inline ? " inline" : "")} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

/** Карта колоды: код, заголовок, пояснение. */
export function CardBlock({ label, code, title, note }: { label: string; code?: string; title?: string; note?: string }) {
  return (
    <Section>
      <Label>{label}{code ? ` · ${code}` : ""}</Label>
      {title && <div className="h2">{title}</div>}
      {note && <div className="muted small">{note}</div>}
    </Section>
  );
}

const two = (n: number) => String(n).padStart(2, "0");

export function fmtDeadline(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const time = `${two(d.getHours())}:${two(d.getMinutes())}`;
  const sameDay = d.toDateString() === now.toDateString();
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1);
  if (sameDay) return `сегодня в ${time}`;
  if (d.toDateString() === tomorrow.toDateString()) return `завтра в ${time}`;
  return `${two(d.getDate())}.${two(d.getMonth() + 1)} в ${time}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${two(d.getDate())}.${two(d.getMonth() + 1)} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

/** Остаток окна — спокойно, без нагнетания: «осталось 4 ч 10 мин». */
export function Remaining({ iso }: { iso: string | null | undefined }) {
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 30_000); return () => clearInterval(t); }, []);
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return <span className="meta">окно закрылось</span>;
  const m = Math.floor(ms / 60_000);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  const text = d >= 1 ? `${d} д ${h % 24} ч` : h >= 1 ? `${h} ч ${m % 60} мин` : `${m} мин`;
  return <span className="meta">осталось {text}</span>;
}

export function ErrorLine({ error }: { error: string | null }) {
  return error ? <div className="error">{error}</div> : null;
}

/** Пока на экране несохранённый текст, случайное закрытие Mini App требует подтверждения. */
export function useDraftGuard(active: boolean): void {
  useEffect(() => {
    guardDraft(active);
    return () => guardDraft(false);
  }, [active]);
}

export function wordCount(s: string): number {
  return s.trim() ? s.trim().split(/\s+/).length : 0;
}
