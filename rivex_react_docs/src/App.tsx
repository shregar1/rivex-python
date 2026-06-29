import { useEffect, useState, useMemo } from 'react';
import { Sun, Moon, Search, Lock } from 'lucide-react';
import { Virtuoso } from 'react-virtuoso';
import './index.css';
import { EndpointCard } from './components/EndpointCard';
import { CommandPalette } from './components/CommandPalette';
import { AuthModal } from './components/AuthModal';
import type { Endpoint } from './utils/snippetGenerator';

export default function App() {
  const [theme, setTheme] = useState('dark');
  const [specUrl, setSpecUrl] = useState('/openapi.json');
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  
  const [authOpen, setAuthOpen] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem('theme') || 'dark';
    setTheme(t);
    if (t === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
    
    const params = new URLSearchParams(window.location.search);
    const url = params.get('url') || (window as any).__RIVEX_SPEC_URL__ || '/openapi.json';
    setSpecUrl(url);

    fetch(url)
      .then(res => res.json())
      .then(data => {
        const parsed = parseSpec(data);
        setEndpoints(parsed);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setLoading(false);
      });
  }, []);

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('theme', next);
    if (next === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
  };

  const filteredEndpoints = useMemo(() => {
    if (!query) return endpoints;
    const q = query.toLowerCase();
    return endpoints.filter(e => e.path.toLowerCase().includes(q) || e.summary.toLowerCase().includes(q));
  }, [endpoints, query]);

  const parseSpec = (spec: any): Endpoint[] => {
    const eps: Endpoint[] = [];
    if (!spec.paths) return eps;
    
    const resolveSchema = (ref: string) => {
      if (!ref) return null;
      const parts = ref.replace('#/', '').split('/');
      let curr = spec;
      for (const p of parts) {
        if (!curr[p]) return null;
        curr = curr[p];
      }
      return curr;
    };

    const collectSchemas = (schema: any, collected: Record<string, any>) => {
      if (!schema) return;
      if (schema.$ref) {
        const name = schema.$ref.split('/').pop()!;
        if (!collected[name]) {
          const resolved = resolveSchema(schema.$ref);
          collected[name] = resolved;
          collectSchemas(resolved, collected);
        }
      }
      if (schema.type === 'array' && schema.items) collectSchemas(schema.items, collected);
      if (schema.type === 'object' && schema.properties) {
        Object.values(schema.properties).forEach(p => collectSchemas(p, collected));
      }
      if (schema.anyOf) schema.anyOf.forEach((s: any) => collectSchemas(s, collected));
    };

    for (const [path, methods] of Object.entries(spec.paths)) {
      for (const [method, op] of Object.entries(methods as any) as [string, any][]) {
        const e: Endpoint = {
          id: `${method}-${path}`,
          method: method.toUpperCase(),
          path,
          summary: op.summary || '',
          params: op.parameters || [],
          responses: op.responses || {},
          usedSchemas: {}
        };
        
        if (op.requestBody?.content?.['application/json']) {
          e.requestBody = op.requestBody.content['application/json'].schema;
          collectSchemas(e.requestBody, e.usedSchemas);
        }
        
        if (e.responses['200']?.content?.['application/json']) {
          collectSchemas(e.responses['200'].content['application/json'].schema, e.usedSchemas);
        }
        
        eps.push(e);
      }
    }
    return eps;
  };

  const handleNavClick = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <>
      <AuthModal isOpen={authOpen} onClose={() => setAuthOpen(false)} />
      <CommandPalette endpoints={endpoints} onSelect={handleNavClick} />

      <header className="topbar">
        <div className="brand">
          RIV<span className="accent">E</span>X
        </div>
        <div className="links">
          <button className="btn" onClick={() => setAuthOpen(true)} title="Set global API Key / Auth Token">
            <Lock size={14} style={{ marginRight: '4px' }} /> Auth
          </button>
          <a className="btn" href={specUrl} target="_blank" rel="noreferrer">OpenAPI JSON</a>
          <button className="btn theme-toggle" onClick={toggleTheme}>
            {theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}
            <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
          </button>
        </div>
      </header>

      <main className="layout">
        <aside className="sidebar">
          <div className="search-container">
            <Search />
            <input 
              className="search" 
              type="search" 
              placeholder="Search (Cmd+K)" 
              value={query}
              onChange={e => setQuery(e.target.value)}
              onClick={() => {
                // Let Cmd+K handle the global search, but allow local filter too
              }}
            />
          </div>
          <div className="nav-title">Routes</div>
          <nav>
            {filteredEndpoints.map(e => (
              <a 
                key={e.id}
                href={`#${e.id}`} 
                className="nav-link"
                onClick={(ev) => {
                  ev.preventDefault();
                  handleNavClick(e.id);
                }}
              >
                <span className={`method method-${e.method}`}>{e.method}</span>
                <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{e.path}</span>
              </a>
            ))}
          </nav>
        </aside>

        <section className="content" style={{ padding: '2rem', flex: 1, minWidth: 0, overflow: 'auto' }}>
          <div className="section-head" style={{ marginBottom: '2rem' }}>
            <h2>API Reference</h2>
            <div className="count">{filteredEndpoints.length} endpoints</div>
            <p style={{ color: '#888', marginTop: '0.5rem' }}>Press <kbd style={{ background: '#eee', color: '#333', padding: '2px 6px', borderRadius: '4px' }}>Cmd + K</kbd> to search everywhere.</p>
          </div>
          
          {loading && <div className="empty">Loading documentation...</div>}
          
          {!loading && (
            <Virtuoso
              useWindowScroll
              data={filteredEndpoints}
              itemContent={(_idx, e) => <EndpointCard key={e.id} e={e} specUrl={specUrl} />}
            />
          )}
        </section>
      </main>
    </>
  );
}
