import React, { useState } from 'react';
import BACKEND_API, { parseApiError } from '../api';
import { useAuth } from '../context/AuthContext';

const AddContentPage: React.FC = () => {
    const [text, setText] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState({ type: '', text: '' });
    const { token } = useAuth();

    const apiBase = BACKEND_API;

    const showMessage = (type: string, text: string) => {
        setMessage({ type, text });
        setTimeout(() => setMessage({ type: '', text: '' }), 5000);
    };

    const handleIngest = async () => {
        if (!text.trim()) return;
        setLoading(true);
        try {
            const res = await fetch(`${apiBase}/ingest`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    text,
                    source: 'UI'
                }),
            });
            if (res.ok) {
                showMessage('success', 'Information added successfully! It is now part of my knowledge base.');
                setText('');
            } else {
                const detail = await parseApiError(res);
                throw new Error(detail);
            }
        } catch (err) {
            const msg = err instanceof Error ? err.message : 'Failed to add content.';
            showMessage('error', msg);
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="container">
            <div className="card" style={{ maxWidth: '800px', margin: '0 auto', width: '100%' }}>
                <h2>📚 Add Knowledge Base</h2>
                <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                    Paste articles, paragraphs, or any text information here. We will chunk it and store it in the vector database for RAG.
                </p>

                {message.text && (
                    <div style={{
                        padding: '1rem',
                        borderRadius: '8px',
                        backgroundColor: message.type === 'success' ? '#dcfce7' : '#fee2e2',
                        color: message.type === 'success' ? '#166534' : '#991b1b',
                        marginBottom: '1rem',
                    }}>
                        {message.text}
                    </div>
                )}

                <div className="ingest-section">
                    <label style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.4rem' }}>Content Paragraph</label>
                    <textarea
                        placeholder="Paste your text information here..."
                        style={{ minHeight: '400px', resize: 'vertical', marginBottom: '1.5rem' }}
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                    />

                    <button className="btn" onClick={handleIngest} disabled={loading || !text.trim()}>
                        {loading ? <span className="loading-spinner"></span> : 'Index Information'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AddContentPage;
