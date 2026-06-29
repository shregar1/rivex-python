import { useState, useEffect } from 'react';

export function AuthModal({ isOpen, onClose }: { isOpen: boolean, onClose: () => void }) {
  const [token, setToken] = useState('');

  useEffect(() => {
    setToken(sessionStorage.getItem('rivex_auth_token') || '');
  }, [isOpen]);

  if (!isOpen) return null;

  const save = () => {
    sessionStorage.setItem('rivex_auth_token', token);
    onClose();
  };

  const clear = () => {
    sessionStorage.removeItem('rivex_auth_token');
    setToken('');
    onClose();
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    }}>
      <div style={{
        backgroundColor: '#fff', padding: '2rem', borderRadius: '8px',
        width: '400px', maxWidth: '90%', boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
      }}>
        <h2 style={{ margin: '0 0 1rem 0' }}>Authentication</h2>
        <p style={{ color: '#666', fontSize: '14px', marginBottom: '1.5rem' }}>
          Set your Bearer Token or API Key. It will be injected into all requests.
        </p>
        
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 600 }}>Authorization Header Value</label>
        <input 
          type="text" 
          placeholder="Bearer YOUR_TOKEN_HERE" 
          value={token}
          onChange={(e) => setToken(e.target.value)}
          style={{
            width: '100%', padding: '0.75rem', borderRadius: '4px',
            border: '1px solid #ccc', marginBottom: '1.5rem',
            fontFamily: 'monospace'
          }}
        />

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
          <button onClick={clear} style={{ 
            padding: '0.5rem 1rem', background: '#f5f5f5', border: 'none', 
            borderRadius: '4px', cursor: 'pointer', color: '#dc2626'
          }}>Clear</button>
          
          <button onClick={onClose} style={{ 
            padding: '0.5rem 1rem', background: '#fff', border: '1px solid #ccc', 
            borderRadius: '4px', cursor: 'pointer' 
          }}>Cancel</button>

          <button onClick={save} style={{ 
            padding: '0.5rem 1rem', background: 'var(--brand-color)', border: 'none', 
            borderRadius: '4px', cursor: 'pointer', color: 'white', fontWeight: 600
          }}>Save</button>
        </div>
      </div>
    </div>
  );
}
