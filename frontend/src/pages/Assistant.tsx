import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Calculator, Send, Sparkles, User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PageHeader, SimpleTable } from "@/components/common";
import { useApiQuery } from "@/hooks/useApi";
import { api } from "@/services/api";
import { cn } from "@/lib/utils";

interface Answer {
  intent: string; answer: string; table: { columns: string[]; rows: (string | number)[][] } | null; mode: string;
  ai_explanation?: string | null; ai_error?: string | null; examples?: string[]; data_through?: string;
}
type Msg = { role: "user"; text: string } | { role: "assistant"; a: Answer } | { role: "error"; text: string };

export default function Assistant() {
  const { data: info } = useApiQuery<{ llm_configured: boolean; provider: string | null; examples: string[] }>(["assistant-info"], "/assistant/info");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy]);

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const a = await api.post<Answer>("/assistant/ask", { question });
      setMsgs((m) => [...m, { role: "assistant", a }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "error", text: (e as Error).message }]);
    } finally { setBusy(false); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); void ask(q); };

  return (
    <div className="flex h-[calc(100dvh-8.5rem)] min-h-[520px] flex-col animate-fade-in">
      <PageHeader title="AI Business Assistant" icon={<Bot className="h-6 w-6 text-primary" />}
        description="Ask questions in plain English. Answers come from read-only, pre-defined analytical functions; your text is never run as SQL."
        actions={<Badge variant={info?.llm_configured ? "success" : "secondary"}>{info?.llm_configured ? <><Sparkles /> LLM explanations on ({info.provider})</> : <><Calculator /> Rule-based mode (no LLM key)</>}</Badge>} />
      <Card className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-3 scrollbar-thin sm:p-5" aria-live="polite">
          {msgs.length === 0 && (
            <div className="mx-auto max-w-2xl py-6 text-center">
              <div className="mx-auto mb-3 w-fit rounded-2xl bg-primary/10 p-3 text-primary"><Bot className="h-7 w-7" /></div>
              <h2 className="font-semibold">What would you like to know?</h2>
              <p className="mt-1 text-sm text-muted-foreground">Try one of these:</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {(info?.examples ?? []).map((e) => (
                  <button key={e} onClick={() => ask(e)} className="rounded-xl border bg-background p-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent">{e}</button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) => m.role === "user" ? (
            <div key={i} className="flex justify-end gap-2">
              <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">{m.text}</div>
              <span className="mt-1 hidden rounded-full bg-muted p-1.5 sm:block"><UserIcon className="h-4 w-4" /></span>
            </div>
          ) : m.role === "error" ? (
            <div key={i} className="rounded-xl bg-critical/10 px-4 py-2.5 text-sm text-critical">{m.text}</div>
          ) : (
            <div key={i} className="flex gap-2">
              <span className="mt-1 hidden h-fit rounded-full bg-primary/10 p-1.5 text-primary sm:block"><Bot className="h-4 w-4" /></span>
              <div className="min-w-0 max-w-full flex-1 space-y-3 sm:max-w-[90%]">
                <div className="rounded-2xl rounded-tl-sm border bg-background px-4 py-3">
                  <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"><Calculator className="h-3.5 w-3.5" /> Calculated result{m.a.data_through && <span className="font-normal normal-case">· data to {m.a.data_through}</span>}</p>
                  <div className="prose-sm text-sm leading-relaxed [&_strong]:font-semibold"><ReactMarkdown>{m.a.answer}</ReactMarkdown></div>
                  {m.a.table && <div className="mt-3"><SimpleTable maxHeight={320} columns={m.a.table.columns} rows={m.a.table.rows.map((r) => r.map((c) => String(c)))} /></div>}
                </div>
                {m.a.ai_explanation && (
                  <div className="rounded-2xl border border-dashed border-primary/40 bg-primary/5 px-4 py-3">
                    <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-primary"><Sparkles className="h-3.5 w-3.5" /> AI-generated explanation</p>
                    <div className="text-sm leading-relaxed"><ReactMarkdown>{m.a.ai_explanation}</ReactMarkdown></div>
                  </div>
                )}
                {m.a.ai_error && <p className="text-xs text-muted-foreground">{m.a.ai_error}</p>}
                {m.a.examples && m.a.intent === "help" && (
                  <div className="flex flex-wrap gap-1.5">{m.a.examples.slice(0, 4).map((e) => <button key={e} onClick={() => ask(e)} className="rounded-full border px-3 py-1 text-xs hover:bg-accent">{e}</button>)}</div>
                )}
              </div>
            </div>
          ))}
          {busy && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Bot className="h-4 w-4 animate-pulse text-primary" /> Analysing your data…</div>}
          <div ref={end} />
        </div>
        <CardContent className="border-t p-3">
          <form onSubmit={submit} className="flex gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Which products need restocking?" maxLength={500} aria-label="Your question" />
            <Button type="submit" disabled={!q.trim()} loading={busy} className={cn("shrink-0")} aria-label="Send"><Send /><span className="hidden sm:inline">Ask</span></Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
