import React, { useState } from 'react';
import { AdkHealthResponse, sendAdkCopilotMessage } from '../services/adkClient';
import { GitHubUser } from '../types/auth';

interface CopilotMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode?: string;
  toolCalls?: string[];
  timestamp: string;
}

interface AdkCopilotDrawerProps {
  open: boolean;
  onClose: () => void;
  health: AdkHealthResponse;
  user?: GitHubUser | null;
  onSelectExperiment?: (expId: string) => void;
}

const QUICK_PROMPTS = [
  'Optimize top high-bounce segment (EXP-0057 / SEG-057)',
  'Test SKU-0017 95% prompt injection guardrail',
  'Sync campaign with Sister Table 1 (A2A <= €25 CPM)',
  'Recommend Mediterranean_Warm SKUs with >= 15pt margin buffer'
];

export const AdkCopilotDrawer: React.FC<AdkCopilotDrawerProps> = ({
  open,
  onClose,
  health,
  user,
  onSelectExperiment
}) => {
  const [messages, setMessages] = useState<CopilotMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        'Connected to `expedition_t02` (Dynamic Storefront Engine). Ask me to audit `seed_t02` high-bounce segments, verify `SKU-0017` prompt-injection defense and the `<= 30%` discount cap, render a hero lifestyle visual (`GEMINI_IMAGE_MODEL`), or trigger the `STOREFRONT_TO_CAMPAIGN_SYNC` A2A handshake with Sister Table 1.',
      mode: health.connected ? 'adk_live' : 'deterministic_tool_pipeline',
      toolCalls: ['recommend_storefront_optimization', 'render_storefront_preview'],
      timestamp: 'Ready'
    }
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  if (!open) return null;

  const handleSend = async (promptText?: string) => {
    const text = (promptText ?? input).trim();
    if (!text || sending) return;
    if (!promptText) setInput('');

    const userMsg: CopilotMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);

    const res = await sendAdkCopilotMessage(text);
    const assistantMsg: CopilotMessage = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: res.reply,
      mode: res.mode,
      toolCalls: res.tool_calls,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setSending(false);
  };

  return (
    <div
      className="copilot-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className="copilot-drawer" aria-label="ADK Agent Copilot">
        <div className="copilot-head">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className={`status-dot ${health.connected ? 'online' : ''}`} />
              <span style={{ fontWeight: 500, fontSize: '0.9375rem' }}>
                ADK Copilot · <span className="mono">{health.agent_name}</span>
              </span>
            </div>
            <div className="muted" style={{ fontSize: '0.75rem', marginTop: 2 }}>
              Pack <span className="mono">{health.seed_pack}</span> · Model{' '}
              <span className="mono">{health.gemini_model}</span> · Image{' '}
              <span className="mono">{health.gemini_image_model}</span>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>
            Esc · Close
          </button>
        </div>

        <div
          style={{
            padding: '10px 20px',
            borderBottom: '1px solid var(--color-border-subtle)',
            background: 'rgba(145, 132, 217, 0.05)',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 6
          }}
        >
          {QUICK_PROMPTS.map((q) => (
            <button
              key={q}
              type="button"
              className="btn-ghost"
              style={{ fontSize: '0.72rem', padding: '4px 8px' }}
              onClick={() => handleSend(q)}
              disabled={sending}
            >
              {q}
            </button>
          ))}
        </div>

        <div className="copilot-messages">
          {messages.map((m) => (
            <div key={m.id} className={`copilot-msg ${m.role}`}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 4,
                  fontSize: '0.6875rem',
                  color: 'var(--color-text-subtle)'
                }}
              >
                <span className="mono">
                  {m.role === 'assistant'
                    ? `ADK · ${m.mode || 'tool_pipeline'}`
                    : user
                    ? `${user.name} (@${user.username})`
                    : 'Operator'}
                </span>
                <span className="mono">{m.timestamp}</span>
              </div>
              <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
              {m.toolCalls && m.toolCalls.length > 0 && (
                <div className="copilot-tools">
                  {m.toolCalls.map((tool) => (
                    <span key={tool} className="copilot-tool-pill">
                      fn:{tool}()
                    </span>
                  ))}
                </div>
              )}
              {m.role === 'assistant' && m.content.includes('EXP-0057') && onSelectExperiment && (
                <div style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    className="btn-ghost"
                    style={{ fontSize: '0.72rem', padding: '3px 8px' }}
                    onClick={() => {
                      onSelectExperiment('EXP-0057');
                      onClose();
                    }}
                  >
                    Inspect EXP-0057 in Storefront Preview →
                  </button>
                </div>
              )}
            </div>
          ))}
          {sending && (
            <div className="copilot-msg assistant">
              <span className="mono muted" style={{ fontSize: '0.75rem' }}>
                Running ADK tool pipeline (BigQuery / FastMCP)...
              </span>
            </div>
          )}
        </div>

        <form
          className="copilot-foot"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <input
            type="text"
            className="copilot-input"
            placeholder="Ask expedition_t02 about segments, SKUs, guardrails or A2A..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
          />
          <button type="submit" className="btn-primary" disabled={sending || !input.trim()}>
            Send
          </button>
        </form>
      </aside>
    </div>
  );
};
