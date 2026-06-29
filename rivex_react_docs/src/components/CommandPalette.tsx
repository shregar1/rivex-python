import { useState, useEffect } from 'react';
import { Command } from 'cmdk';
import type { Endpoint } from '../utils/snippetGenerator';

export function CommandPalette({ endpoints, onSelect }: { endpoints: Endpoint[], onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };

    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, []);

  if (!open) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 2000,
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      paddingTop: '10vh'
    }}>
      <div style={{
        backgroundColor: '#fff', borderRadius: '8px',
        width: '600px', maxWidth: '90%', boxShadow: '0 16px 48px rgba(0,0,0,0.2)',
        overflow: 'hidden'
      }}>
        <Command label="Command Menu" loop>
          <Command.Input 
            placeholder="Search API endpoints (Cmd+K)..." 
            style={{
              width: '100%', padding: '1rem', border: 'none', borderBottom: '1px solid #eaeaea',
              fontSize: '1.1rem', outline: 'none'
            }}
            autoFocus
          />
          <Command.List style={{ maxHeight: '400px', overflowY: 'auto', padding: '0.5rem' }}>
            <Command.Empty style={{ padding: '2rem', textAlign: 'center', color: '#888' }}>
              No endpoints found.
            </Command.Empty>

            <Command.Group heading="Endpoints" style={{ color: '#888', padding: '0.5rem', fontSize: '0.8rem', textTransform: 'uppercase' }}>
              {endpoints.map((e) => (
                <Command.Item 
                  key={e.id}
                  value={`${e.method} ${e.path} ${e.summary}`}
                  onSelect={() => {
                    onSelect(e.id);
                    setOpen(false);
                  }}
                  style={{
                    padding: '0.75rem', borderRadius: '4px', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: '1rem',
                    color: '#000', fontSize: '0.9rem'
                  }}
                  // Using inline style for hover requires extra effort, rely on CSS class if possible,
                  // but we'll keep it simple: cmdk provides data-selected
                  className="cmdk-item"
                >
                  <span className={`method-pill method-${e.method.toLowerCase()}`} style={{ fontSize: '0.7rem', padding: '2px 6px' }}>
                    {e.method}
                  </span>
                  <span style={{ fontFamily: 'monospace', color: '#555' }}>{e.path}</span>
                  <span style={{ color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {e.summary}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
