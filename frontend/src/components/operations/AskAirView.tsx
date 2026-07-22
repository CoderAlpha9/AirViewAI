import { useEffect, useMemo, useRef, useState } from "react";

import {
  askCopilot,
  copilotError,
  getCopilotStatus,
  type CopilotReply,
  type CopilotStatus,
} from "../../api/copilot";
import type { Horizon, Pollutant } from "../../api/live";

type ChatMessage =
  | { id: string; role: "user"; content: string; contextKey: string }
  | { id: string; role: "assistant"; content: string; contextKey: string; reply: CopilotReply }
  | { id: string; role: "system"; content: string; contextKey: string };

interface AskAirViewProps {
  cityName: string;
  cityId?: string;
  pollutant: Pollutant;
  horizon: Horizon;
  snapshotId?: string;
}

const STORAGE_KEY = "airview-copilot-conversation-v1";
const SESSION_KEY = "airview-copilot-session-v1";

function id() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function sessionId() {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const created = id().replace(/[^a-zA-Z0-9_-]/g, "");
    sessionStorage.setItem(SESSION_KEY, created);
    return created;
  } catch {
    return id().replace(/[^a-zA-Z0-9_-]/g, "");
  }
}

function storedMessages(): ChatMessage[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is ChatMessage =>
        typeof item === "object" && item !== null && "role" in item && "content" in item,
    ).slice(-20);
  } catch {
    return [];
  }
}

function pollutantLabel(pollutant: Pollutant) {
  return pollutant === "pm2_5" ? "PM2.5" : "PM10";
}

function detectLanguage(question: string) {
  return /hindi|हिंदी/i.test(question) ? "Hindi" : undefined;
}

export function AskAirView({ cityName, cityId, pollutant, horizon, snapshotId }: AskAirViewProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(storedMessages);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [status, setStatus] = useState<CopilotStatus>();
  const [statusLoading, setStatusLoading] = useState(false);
  const session = useRef(sessionId());
  const requestController = useRef<AbortController | undefined>(undefined);
  const requestGeneration = useRef(0);
  const previousIdentity = useRef("");
  const activeRequestKey = useRef("");
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const identity = `${cityId ?? cityName}|${pollutant}|${horizon}`;
  const requestKey = `${identity}|${snapshotId ?? "loading"}`;
  activeRequestKey.current = requestKey;
  const contextChip = `${cityName} · ${pollutantLabel(pollutant)} · Next ${horizon} hours`;
  const suggestedQuestions = useMemo(
    () => [
      "Why is the forecast rising?",
      "Which areas need attention?",
      "What actions are recommended?",
      `Explain ${cityName}'s outlook in Hindi.`,
    ],
    [cityName],
  );

  useEffect(() => {
    requestGeneration.current += 1;
    requestController.current?.abort();
    setLoading(false);
    setError("");
  }, [requestKey]);

  useEffect(() => {
    if (open && previousIdentity.current && previousIdentity.current !== identity) {
      const contextMessage: ChatMessage = {
        id: id(),
        role: "system",
        content: `Context updated to ${contextChip}.`,
        contextKey: identity,
      };
      setMessages((current) => {
        const previous = current[current.length - 1];
        if (previous?.role === "system" && previous.content === contextMessage.content) return current;
        if (previous?.role === "system" && previous.content.startsWith("Context updated to ")) {
          return [...current.slice(0, -1), contextMessage].slice(-20);
        }
        return [...current, contextMessage].slice(-20);
      });
    }
    previousIdentity.current = identity;
  }, [contextChip, identity, open]);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-20)));
    } catch {
      // Conversation persistence is optional when browser storage is unavailable.
    }
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setStatusLoading(true);
    void getCopilotStatus(controller.signal)
      .then(setStatus)
      .catch(() => setStatus(undefined))
      .finally(() => {
        if (!controller.signal.aborted) setStatusLoading(false);
      });
    window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => controller.abort();
  }, [open]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [loading, messages]);

  useEffect(() => () => requestController.current?.abort(), []);

  const close = () => {
    requestController.current?.abort();
    setLoading(false);
    setOpen(false);
  };

  const send = async (question: string) => {
    const cleanQuestion = question.trim();
    if (!cleanQuestion || loading) return;
    if (!cityId || !snapshotId) {
      setError("The current dashboard snapshot is still loading.");
      return;
    }
    if (status && (!status.enabled || !status.configured)) {
      setError("Ask AirView is not available on this deployment.");
      return;
    }
    const contextAtSend = requestKey;
    const generation = ++requestGeneration.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const history = messages
      .filter(
        (item): item is Extract<ChatMessage, { role: "user" | "assistant" }> =>
          item.contextKey === identity && item.role !== "system",
      )
      .slice(-4)
      .map((item) => ({ role: item.role, content: item.content }));
    const userMessage: ChatMessage = {
      id: id(),
      role: "user",
      content: cleanQuestion,
      contextKey: identity,
    };
    setMessages((current) => [...current, userMessage].slice(-20));
    setInput("");
    setError("");
    setLastQuestion(cleanQuestion);
    setLoading(true);
    try {
      const reply = await askCopilot(
        {
          message: cleanQuestion,
          city_id: cityId,
          pollutant,
          horizon,
          snapshot_id: snapshotId,
          session_id: session.current,
          language: detectLanguage(cleanQuestion),
          history,
        },
        controller.signal,
      );
      if (
        controller.signal.aborted
        || generation !== requestGeneration.current
        || contextAtSend !== activeRequestKey.current
      ) return;
      const assistantMessage: ChatMessage = {
        id: id(),
        role: "assistant",
        content: reply.answer,
        reply,
        contextKey: identity,
      };
      setMessages((current) => [...current, assistantMessage].slice(-20));
    } catch (caught) {
      if (!controller.signal.aborted && generation === requestGeneration.current) {
        setError(copilotError(caught));
      }
    } finally {
      if (generation === requestGeneration.current) setLoading(false);
    }
  };

  const handlePanelKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab" || !panelRef.current) return;
    const focusable = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      ),
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="ask-airview-shell">
      {!open && (
        <button className="ask-airview-launcher" onClick={() => setOpen(true)} aria-label="Open Ask AirView">
          <span aria-hidden="true">?</span> Ask AirView
        </button>
      )}
      {open && (
        <div
          className="ask-airview-panel"
          role="dialog"
          aria-modal="true"
          aria-label="Ask AirView"
          ref={panelRef}
          onKeyDown={handlePanelKeyDown}
        >
          <header className="ask-airview-header">
            <div>
              <strong>Ask AirView</strong>
              <span>Grounded dashboard guidance</span>
            </div>
            <div className="ask-airview-header-actions">
              <button
                onClick={() => {
                  setMessages([]);
                  setError("");
                }}
                aria-label="Clear conversation"
                title="Clear conversation"
              >
                Clear
              </button>
              <button onClick={close} aria-label="Close Ask AirView" title="Close">×</button>
            </div>
          </header>
          <div className="ask-airview-context" title={contextChip}>{contextChip}</div>
          <div className="ask-airview-conversation" ref={scrollRef} aria-live="polite">
            {!messages.length && (
              <div className="ask-airview-intro">
                <strong>Ask about this dashboard</strong>
                <p>Explore current conditions, the forecast, mapped areas, source evidence and recommended actions.</p>
              </div>
            )}
            {messages.map((message) =>
              message.role === "system" ? (
                <p className="ask-airview-system" key={message.id}>{message.content}</p>
              ) : message.role === "user" ? (
                <div className="ask-airview-message ask-airview-user" key={message.id}>{message.content}</div>
              ) : (
                <article className="ask-airview-message ask-airview-assistant" key={message.id}>
                  <p>{message.content}</p>
                  <span className="ask-airview-data-status">{message.reply.data_status}</span>
                  {message.reply.evidence.length > 0 && (
                    <div className="ask-airview-evidence"><strong>Evidence</strong><ul>{message.reply.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>
                  )}
                  {message.reply.limitations.length > 0 && (
                    <details><summary>Data notes</summary><ul>{message.reply.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
                  )}
                  {message.reply.suggested_questions.length > 0 && (
                    <div className="ask-airview-followups">{message.reply.suggested_questions.map((item) => <button key={item} onClick={() => void send(item)}>{item}</button>)}</div>
                  )}
                </article>
              ),
            )}
            {loading && <div className="ask-airview-loading" role="status">Preparing a grounded answer…</div>}
            {error && (
              <div className="ask-airview-error" role="alert">
                <span>{error}</span>
                {lastQuestion && <button onClick={() => void send(lastQuestion)}>Retry</button>}
              </div>
            )}
            {!statusLoading && status && (!status.enabled || !status.configured) && !error && (
              <p className="ask-airview-system">Ask AirView is unavailable on this deployment.</p>
            )}
          </div>
          {!messages.some((message) => message.role === "assistant" && message.contextKey === identity) && (
            <div className="ask-airview-suggestions" aria-label="Suggested questions">
              {suggestedQuestions.map((question) => <button key={question} onClick={() => void send(question)}>{question}</button>)}
            </div>
          )}
          <form
            className="ask-airview-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send(input);
            }}
          >
            <label className="sr-only" htmlFor="ask-airview-input">Question for Ask AirView</label>
            <textarea
              id="ask-airview-input"
              ref={inputRef}
              rows={2}
              maxLength={800}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send(input);
                }
              }}
              placeholder={snapshotId ? "Ask about this dashboard…" : "Waiting for dashboard context…"}
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim() || !snapshotId} aria-label="Send question">Send</button>
          </form>
          <p className="ask-airview-readonly">Read-only decision support · Answers use the selected snapshot</p>
        </div>
      )}
    </div>
  );
}
