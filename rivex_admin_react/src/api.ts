const getHeaders = () => {
  const token = sessionStorage.getItem('rivex_admin_token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  }
  if (token) {
    headers['X-Admin-Token'] = token
  }
  return headers
}

export const fetchMeta = async () => {
  const res = await fetch('/admin/api/meta', { headers: getHeaders() })
  if (!res.ok) {
     if (res.status === 401) throw new Error('401')
     throw new Error('Failed to fetch meta')
  }
  return res.json()
}

export const fetchPartial = async (name: string) => {
  const res = await fetch(`/admin/api/partials/${name}`, { headers: getHeaders() })
  if (!res.ok) {
     if (res.status === 401) throw new Error('401')
     throw new Error('Failed to fetch partial')
  }
  return res.json()
}

export const executeAction = async (name: string, payload?: any) => {
  const res = await fetch(`/admin/api/actions/${name}`, {
    method: 'POST',
    headers: getHeaders(),
    body: payload ? JSON.stringify(payload) : undefined
  })
  if (!res.ok) {
     if (res.status === 401) throw new Error('401')
     throw new Error('Action failed')
  }
  return res.json()
}

export const executeCodegen = async (action: string, payload?: any) => {
  const res = await fetch(`/admin/api/codegen/${action}`, {
    method: 'POST',
    headers: getHeaders(),
    body: payload ? JSON.stringify(payload) : undefined
  })
  if (!res.ok) throw new Error('Codegen failed')
  return res.json()
}
