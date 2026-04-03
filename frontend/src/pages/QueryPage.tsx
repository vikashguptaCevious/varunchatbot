import React, { useState, useEffect, useRef } from 'react';
import BACKEND_API, { parseApiError } from '../api';

interface Metric {
    time_seconds: number;
    tokens: number;
    cost_estimate: number;
}

interface Source {
    text: string;
    metadata: {
        title: string;
        source: string;
        chunk_index: number;
    };
}

interface ChatMessage {
    role: 'user' | 'bot';
    text: string;
    timestamp: number;
    sources?: Source[];
    metrics?: Metric;
    isError?: boolean;
}

const QueryPage: React.FC = () => {
    const [query, setQuery] = useState('');
    const [messages, setMessages] = useState<ChatMessage[]>(() => {
        const saved = sessionStorage.getItem('miniRagChatHistory');
        return saved ? JSON.parse(saved) : [];
    });
    const [loading, setLoading] = useState(false);
    const [abortController, setAbortController] = useState<AbortController | null>(null);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const apiBase = BACKEND_API;

    useEffect(() => {
        sessionStorage.setItem('miniRagChatHistory', JSON.stringify(messages));
        scrollToBottom();
    }, [messages]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const handleQuery = async () => {
        if (!query.trim() || loading) return;

        const userMsg: ChatMessage = {
            role: 'user',
            text: query,
            timestamp: Date.now()
        };

        setMessages(prev => [...prev, userMsg]);
        setQuery('');
        setLoading(true);
        const controller = new AbortController();
        setAbortController(controller);

        try {
            const res = await fetch(`${apiBase}/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: userMsg.text }),
                signal: controller.signal,
            });

            if (res.ok) {
                const data = await res.json();
                const botMsg: ChatMessage = {
                    role: 'bot',
                    text: data.answer,
                    timestamp: Date.now(),
                    sources: data.sources,
                    metrics: data.metrics
                };
                setMessages(prev => [...prev, botMsg]);
            } else {
                const detail = await parseApiError(res);
                throw new Error(detail);
            }
        } catch (err: any) {
            // If user clicked Stop, silently ignore AbortError
            if (err?.name === 'AbortError') {
                console.warn('Query aborted by user');
            } else {
                console.error(err);
                const msg = err instanceof Error ? err.message : String(err);
                const errorMsg: ChatMessage = {
                    role: 'bot',
                    text: msg || "Sorry, I couldn't fetch the answer right now. Please check if the backend is running.",
                    timestamp: Date.now(),
                    isError: true
                };
                setMessages(prev => [...prev, errorMsg]);
            }
        } finally {
            setLoading(false);
            setAbortController(null);
        }
    };

    const handleStop = () => {
        if (abortController) {
            abortController.abort();
        }
    };



    return (
        <div className="container query-page">
            <div className="card chat-card">
                <div className="chat-card-header">
                    <h2>🔍 Ask Knowledge Base</h2>
                </div>

                <div className="chat-history">
                    {messages.length === 0 ? (
                        <div className="empty-state">
                            <p>Hello! Ask me anything based on the documents you've uploaded.</p>
                            <p style={{ fontSize: '0.8rem' }}>I will provide answers with inline citations from your data.</p>
                        </div>
                    ) : (
                        messages.map((msg, idx) => (
                            <div key={idx} className={`message-wrapper ${msg.role}`}>
                                <div className={`message-bubble ${msg.role} ${msg.isError ? 'error' : ''}`}>
                                    <div className="message-text">
                                        {msg.role === 'bot'
                                            ? msg.text.replace(/\[\d+\]/g, '') // Strip [1], [2] etc.
                                            : msg.text}
                                    </div>

                                    {msg.role === 'bot' && msg.metrics && (
                                        <div className="message-footer" style={{ borderTop: 'none', padding: '0.5rem 0 0 0', marginTop: '0.5rem' }}>
                                            <div className="message-metrics">
                                                <span title="Time taken">⏱️ {msg.metrics.time_seconds.toFixed(2)}s</span>
                                                <span title="Token usage">🎫 {msg.metrics.tokens} tokens</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))
                    )}

                    {loading && (
                        <div className="message-wrapper bot">
                            <div className="message-bubble bot thinking">
                                <span className="dot"></span>
                                <span className="dot"></span>
                                <span className="dot"></span>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className="query-input-area">
                    <div className="query-input-row">
                        <input
                            type="text"
                            placeholder="Ask a question..."
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && !loading && handleQuery()}
                            disabled={loading}
                        />
                        {loading ? (
                            <button className="btn btn-stop" type="button" onClick={handleStop}>
                                ■
                            </button>
                        ) : (
                            <button className="btn" type="button" onClick={handleQuery} disabled={!query.trim()}>
                                Send
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default QueryPage;
