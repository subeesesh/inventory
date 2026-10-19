import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import { Bot, SendHorizontal, Sparkles, User } from 'lucide-react';
import api from '../core/api';
import { useApi } from '../core/useApi';
import { DECISION_TYPES } from '../core/constants';
import { date, formatRecommendation, humanize } from '../core/format';
import { Badge, Button, Card, Empty, Markdown } from '../components/ui';

const GREETING = {
  role: 'assistant',
  content: 'Hi — I am the BizTwin copilot. Ask me about stock levels, suppliers, cash, or why AMDIE made a particular decision.',
};

const SUGGESTIONS = [
  'Which products are low on stock?',
  'Which suppliers are least reliable?',
  'What is my current cash position?',
  'Summarise the most recent reorder decision.',
];

export default function Copilot() {
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const decisions = useApi('/tenants/decisions', { initial: [] });
  const twin = useApi('/tenants/twin');
  const bottom = useRef(null);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, sending]);

  const productName = (id) => twin.data?.inventory?.find(p => p.product_id === id)?.name || id;

  const send = async (text) => {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setInput('');
    const next = [...messages, { role: 'user', content }];
    setMessages(next);
    setSending(true);
    try {
      // Send the conversation (minus the canned greeting) so follow-ups have context
      const res = await api.post('/tenants/copilot/chat', { messages: next.slice(1).map(({ role, content: c }) => ({ role, content: c })) });
      setMessages(m => [...m, { role: 'assistant', content: res?.content || 'No answer was returned.' }]);
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', content: `Sorry, that failed: ${e.message}`, error: true }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="grid grid-cols-1 h-[calc(100vh-8.5rem)] min-h-[520px] gap-6 xl:grid-cols-[1fr_320px]">
      <Card padded={false} className="flex min-h-0 flex-col" bodyClassName="flex min-h-0 flex-1 flex-col" title="Copilot" subtitle="Answers grounded in your business twin and decision log" icon={Sparkles}>
        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {messages.map((m, i) => (
            <div key={i} className={clsx('flex gap-3', m.role === 'user' && 'flex-row-reverse')}>
              <span className={clsx('grid size-8 shrink-0 place-items-center rounded-full', m.role === 'user' ? 'bg-primary text-on-primary' : 'bg-surface-2 text-ink-2')}>
                {m.role === 'user' ? <User className="size-4" /> : <Bot className="size-4" />}
              </span>
              <div className={clsx(
                'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm',
                m.role === 'user' ? 'rounded-tr-sm bg-primary text-on-primary' : 'rounded-tl-sm border border-line bg-surface-2',
                m.error && 'border-danger/30 bg-danger-soft text-danger',
              )}>
                {m.role === 'user' ? m.content : <Markdown text={m.content} className={m.error ? 'text-danger' : ''} />}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex gap-3">
              <span className="grid size-8 place-items-center rounded-full bg-surface-2 text-ink-2"><Bot className="size-4" /></span>
              <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-line bg-surface-2 px-4 py-3">
                {[0, 1, 2].map(d => <span key={d} className="size-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${d * 120}ms` }} />)}
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>

        {messages.length === 1 && (
          <div className="flex flex-wrap gap-2 px-5 pb-3">
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => send(s)} className="rounded-full border border-line px-3 py-1.5 text-xs text-ink-2 hover:border-primary hover:text-primary">{s}</button>
            ))}
          </div>
        )}

        <form onSubmit={e => { e.preventDefault(); send(); }} className="flex gap-2 border-t border-line p-4">
          <input
            className="input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about stock, suppliers, cash or a decision…"
            disabled={sending}
          />
          <Button type="submit" icon={SendHorizontal} disabled={!input.trim()} loading={sending}>Send</Button>
        </form>
      </Card>

      <Card title="Ask about a decision" subtitle="Click one to ask the copilot to explain it" padded={false} className="hidden min-h-0 flex-col xl:flex" bodyClassName="min-h-0 flex-1 overflow-y-auto">
        {decisions.data.length === 0 ? <Empty title="No decisions yet" /> : (
          <ul className="divide-y divide-line">
            {decisions.data.slice(0, 12).map(d => {
              const t = DECISION_TYPES[d.decision_type];
              return (
                <li key={d.id}>
                  <button
                    onClick={() => send(`Explain the ${humanize(d.decision_type)} decision for ${productName(d.product_id)} (${d.product_id}) on ${d.date}.`)}
                    className="w-full px-4 py-3 text-left hover:bg-surface-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Badge tone={t?.tone}>{t?.label || humanize(d.decision_type)}</Badge>
                      <span className="text-xs text-muted">{date(d.date)}</span>
                    </div>
                    <p className="mt-1.5 truncate text-sm text-ink">{productName(d.product_id)}</p>
                    <p className="num text-xs text-muted">{formatRecommendation(d.fused_recommendation, d.decision_type)}</p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
