
import { useState, useEffect } from 'react'
import { analyzeSpec, initAgent, sendMessage, authCallback } from './api'
import type { AuthRequirements } from './api'
import { FileJson, Lock, Loader2, Send } from 'lucide-react'
import './index.css'

type Step = 'upload' | 'analyzing' | 'config' | 'initializing' | 'chat'

function App() {
  const [step, setStep] = useState<Step>('upload')
  const [specContent, setSpecContent] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [authReqs, setAuthReqs] = useState<AuthRequirements | null>(null)
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [chatMessage, setChatMessage] = useState('')
  const [chatHistory, setChatHistory] = useState<{role: 'user'|'agent', text: string, authUrl?: string}[]>([])

  // Listen for OAuth completion from popup
  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
        if (event.data.type === 'OAUTH_COMPLETE') {
            const { code, state } = event.data;
            try {
                await authCallback(sessionId, code, state);
                setChatHistory(prev => [...prev, { 
                    role: 'agent', 
                    text: '✅ Authorization received! I am now exchanging the code for an access token... Please send another message to continue.' 
                }]);
            } catch (e) {
                alert("Failed to process authorization code.");
            }
        }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [sessionId]);

  const handleAnalyze = async () => {
    if (!specContent.trim()) return;
    setStep('analyzing')
    try {
        const response = await analyzeSpec(specContent)
        setAuthReqs(response.requirements)
        setSessionId(response.session_id)
        setStep('config')
    } catch (e) {
        alert("Failed to parse spec. Please check JSON format.")
        setStep('upload')
    }
  }

  const handleInit = async () => {
    setStep('initializing')
    try {
        await initAgent(sessionId, credentials)
        setStep('chat')
        setChatHistory([{ role: 'agent', text: 'Agent initialized! I am ready to help you with the API.' }])
    } catch (e) {
        alert("Failed to initialize agent.")
        setStep('config')
    }
  }

  const handleSendMessage = async (customMsg?: string) => {
      const msgText = customMsg || chatMessage;
      if(!msgText.trim()) return;
      
      if (!customMsg) setChatMessage('');
      
      setChatHistory(prev => [...prev, { role: 'user', text: msgText }])
      
      try {
          const result = await sendMessage(sessionId, msgText)
          setChatHistory(prev => [...prev, { role: 'agent', text: result.response, authUrl: result.auth_url }])
      } catch (e) {
          setChatHistory(prev => [...prev, { role: 'agent', text: "Error: Failed to get response from agent." }])
      }
  }

  return (
    <div className="app-container">
      <header style={{ marginBottom: '2rem', textAlign: 'center' }}>
        <h1 style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
           <FileJson size={48} /> OpenAPI<span style={{ color: 'var(--accent-color)' }}>Sandbox</span>
        </h1>
        <p style={{ color: 'var(--text-secondary)' }}>Instantly turn any OpenAPI spec into an actionable AI Agent.</p>
      </header>

      <main>
      {step === 'upload' && (
        <div className="card" style={{ maxWidth: '600px', margin: '0 auto' }}>
            <h2>Upload Specification</h2>
            <p style={{ marginBottom: '1.5rem', fontSize: '0.9rem' }}>Paste your JSON or YAML spec below to get started.</p>
            
            <textarea 
                rows={10} 
                placeholder='{"openapi": "3.0.0", ...}'
                value={specContent}
                onChange={(e) => setSpecContent(e.target.value)}
                style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
            />
            
            <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-end' }}>
                <button onClick={handleAnalyze} disabled={!specContent.trim()}>
                    Analyze Spec
                </button>
            </div>
        </div>
      )}

      {(step === 'analyzing' || step === 'initializing') && (
        <div className="card" style={{ maxWidth: '400px', margin: '0 auto', textAlign: 'center' }}>
            <Loader2 className="loader" size={48} color="var(--accent-color)" />
            <h3 style={{ marginTop: '1rem' }}>
                {step === 'analyzing' ? 'Analyzing Authentication...' : 'Spinning up Agent...'}
            </h3>
            <p style={{ color: 'var(--text-secondary)' }}>This usually takes a few seconds.</p>
        </div>
      )}

      {step === 'config' && authReqs && (
        <div className="card" style={{ maxWidth: '500px', margin: '0 auto', textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                <div style={{ padding: '12px', background: authReqs.type === 'none' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(99, 102, 241, 0.2)', borderRadius: '12px' }}>
                    {authReqs.type === 'none' ? (
                        <Send size={32} color="#10b981" />
                    ) : (
                        <Lock size={32} color="var(--accent-color)" />
                    )}
                </div>
                <div>
                    <h2 style={{ margin: 0, fontSize: '1.5rem' }}>
                        {authReqs.type === 'none' ? 'Ready to Initialize' : 'Authentication Required'}
                    </h2>
                    <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{authReqs.description}</p>
                </div>
            </div>

            {authReqs.fields && authReqs.fields.map(field => (
                <div key={field.name} className="input-group">
                    <label>{field.label}</label>
                    <input 
                        type={field.type} 
                        placeholder={field.name.includes('secret') ? '••••••••' : ''}
                        onChange={(e) => setCredentials(prev => ({ ...prev, [field.name]: e.target.value }))}
                    />
                </div>
            ))}

            <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                   🔒 Credentials are ephemeral & never stored.
                </span>
                <button onClick={handleInit}>
                    Start Agent
                </button>
            </div>
        </div>
      )}

      {step === 'chat' && (
        <div className="card" style={{ maxWidth: '800px', margin: '0 auto', height: '600px', display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
            {/* Chat Header */}
            <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--card-border)', display: 'flex', alignItems: 'center', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981', marginRight: '10px' }}></div>
                <span style={{ fontWeight: 600 }}>API Agent Active</span>
                <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--text-secondary)', border: '1px solid var(--card-border)', padding: '2px 8px', borderRadius: '4px' }}>
                    {authReqs?.type ? authReqs.type.toUpperCase() : 'NO AUTH'} MODE
                </span>
            </div>

            {/* Chat Area */}
            <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {chatHistory.map((msg, idx) => (
                    <div key={idx} style={{ 
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '70%',
                    }}>
                        <div style={{ 
                            padding: '1rem', 
                            borderRadius: msg.role === 'user' ? '16px 16px 0 16px' : '16px 16px 16px 0',
                            background: msg.role === 'user' ? 'var(--accent-color)' : 'rgba(255,255,255,0.1)',
                            color: 'white',
                            lineHeight: '1.5'
                        }}>
                            <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
                            {msg.authUrl && (
                                <div style={{ marginTop: '1rem' }}>
                                    <button 
                                        onClick={() => window.open(msg.authUrl, '_blank', 'width=600,height=600')}
                                        style={{ background: '#10b981', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', width: 'auto', fontSize: '0.9rem' }}
                                    >
                                        <Lock size={16} /> Authorize API
                                    </button>
                                    <p style={{ fontSize: '0.75rem', marginTop: '0.5rem', color: 'var(--text-secondary)', opacity: 0.8 }}>
                                        Authorization needed to continue.
                                    </p>
                                </div>
                            )}
                        </div>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '4px', display: 'block', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                            {msg.role === 'user' ? 'You' : 'Agent'}
                        </span>
                    </div>
                ))}
            </div>

            {/* Input Area */}
            <div style={{ padding: '1rem', borderTop: '1px solid var(--card-border)', background: 'rgba(0,0,0,0.2)', display: 'flex', gap: '1rem' }}>
                <input 
                  type="text" 
                  placeholder="Ask the agent to do something..." 
                  value={chatMessage}
                  onChange={e => setChatMessage(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                  style={{ background: 'rgba(255,255,255,0.05)', border: 'none' }}
                />
                <button onClick={() => handleSendMessage()} style={{ padding: '0 1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Send size={20} />
                </button>
            </div>
        </div>
      )}
      </main>
    </div>
  )
}

export default App
