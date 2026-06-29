import { useState, useRef } from 'react';
import Editor from '@monaco-editor/react';
import type { Endpoint } from '../utils/snippetGenerator';
import { generateCurl, generatePython, generateJS } from '../utils/snippetGenerator';

export function EndpointCard({ e, specUrl }: { e: Endpoint, specUrl: string }) {
  const [inputs, setInputs] = useState<Record<string, string>>({});
  
  // Set initial reqBody if schema is available
  const [reqBody, setReqBody] = useState<string>(() => {
    if (e.requestBody) {
      return JSON.stringify({ example: "data" }, null, 2); // Simple placeholder
    }
    return '';
  });

  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'curl' | 'python' | 'js'>('curl');

  const containerRef = useRef<HTMLDivElement>(null);

  const authHeader = sessionStorage.getItem('rivex_auth_token') || undefined;

  const execute = async () => {
    setLoading(true);
    setResponse(null);
    let url = specUrl.replace('/openapi.json', '') + e.path;
    const qp = new URLSearchParams();
    
    const headers: Record<string, string> = { "Accept": "application/json" };
    if (authHeader) headers["Authorization"] = authHeader;

    e.params.forEach(p => {
      const val = inputs[p.name];
      if (val) {
        if (p.in === 'path') url = url.replace(`{${p.name}}`, encodeURIComponent(val));
        if (p.in === 'query') qp.append(p.name, val);
        if (p.in === 'header') headers[p.name] = val;
      }
    });

    if (e.requestBody && reqBody) {
      headers['Content-Type'] = 'application/json';
    }

    if (qp.toString()) url += '?' + qp.toString();

    try {
      const res = await fetch(url, {
        method: e.method,
        headers,
        body: e.requestBody && reqBody ? reqBody : undefined
      });
      const data = await res.json().catch(() => null);
      setResponse(JSON.stringify({ status: res.status, data: data || 'No JSON response' }, null, 2));
    } catch (err: any) {
      setResponse(err.toString());
    }
    setLoading(false);
  };

  const getSnippet = () => {
    if (activeTab === 'curl') return generateCurl(e, specUrl, inputs, reqBody, authHeader);
    if (activeTab === 'python') return generatePython(e, specUrl, inputs, reqBody, authHeader);
    if (activeTab === 'js') return generateJS(e, specUrl, inputs, reqBody, authHeader);
    return '';
  };

  return (
    <div id={e.id} ref={containerRef} className="endpoint-card" style={{ marginBottom: '2rem', padding: '1rem', border: '1px solid #eaeaea', borderRadius: '8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
        <span className={`method-pill method-${e.method.toLowerCase()}`}>{e.method}</span>
        <h3 style={{ margin: 0, fontFamily: 'monospace' }}>{e.path}</h3>
      </div>
      <p style={{ color: '#555' }}>{e.summary}</p>

      {e.params.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <h4>Parameters</h4>
          {e.params.map(p => (
            <div key={p.name} style={{ display: 'flex', gap: '1rem', marginBottom: '0.5rem', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, width: '120px' }}>{p.name}</span>
              <span style={{ color: '#888', fontSize: '0.8rem', width: '60px' }}>({p.in})</span>
              <input 
                type="text" 
                placeholder={`Value for ${p.name}`}
                value={inputs[p.name] || ''}
                onChange={ev => setInputs({ ...inputs, [p.name]: ev.target.value })}
                style={{ flex: 1, padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px' }}
              />
            </div>
          ))}
        </div>
      )}

      {e.requestBody && (
        <div style={{ marginBottom: '1rem' }}>
          <h4>Request Body (JSON)</h4>
          <div style={{ border: '1px solid #eaeaea', borderRadius: '4px', overflow: 'hidden' }}>
            <Editor
              height="200px"
              defaultLanguage="json"
              value={reqBody}
              onChange={(val) => setReqBody(val || '')}
              theme="light"
              options={{ minimap: { enabled: false }, scrollBeyondLastLine: false }}
            />
          </div>
        </div>
      )}

      <div style={{ marginBottom: '1rem', marginTop: '1.5rem', background: '#f5f5f5', padding: '1rem', borderRadius: '8px' }}>
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem', borderBottom: '1px solid #ddd', paddingBottom: '0.5rem' }}>
          <button 
            style={{ background: 'none', border: 'none', fontWeight: activeTab === 'curl' ? 600 : 400, cursor: 'pointer', borderBottom: activeTab === 'curl' ? '2px solid var(--brand-color)' : 'none' }}
            onClick={() => setActiveTab('curl')}
          >cURL</button>
          <button 
            style={{ background: 'none', border: 'none', fontWeight: activeTab === 'python' ? 600 : 400, cursor: 'pointer', borderBottom: activeTab === 'python' ? '2px solid var(--brand-color)' : 'none' }}
            onClick={() => setActiveTab('python')}
          >Python</button>
          <button 
            style={{ background: 'none', border: 'none', fontWeight: activeTab === 'js' ? 600 : 400, cursor: 'pointer', borderBottom: activeTab === 'js' ? '2px solid var(--brand-color)' : 'none' }}
            onClick={() => setActiveTab('js')}
          >JavaScript</button>
        </div>
        <pre className="curl-box" style={{ background: '#1e1e1e', color: '#d4d4d4', padding: '1rem', borderRadius: '4px', overflowX: 'auto', fontSize: '0.85rem' }}>
          {getSnippet()}
        </pre>
      </div>

      <button className="execute-btn" onClick={execute} disabled={loading} style={{ width: '100%', padding: '0.75rem', background: 'var(--brand-color)', color: 'white', border: 'none', borderRadius: '4px', fontWeight: 'bold', cursor: loading ? 'wait' : 'pointer' }}>
        {loading ? 'Executing...' : 'Try it out 🚀'}
      </button>

      {response && (
        <div style={{ marginTop: '1rem' }}>
          <h4>Response</h4>
          <Editor
              height="200px"
              defaultLanguage="json"
              value={response}
              theme="vs-dark"
              options={{ readOnly: true, minimap: { enabled: false }, scrollBeyondLastLine: false }}
          />
        </div>
      )}
    </div>
  );
}
