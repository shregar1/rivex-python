import { useState } from 'react'
import { useAdminStore } from '../store'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Server } from 'lucide-react'

export function Login() {
  const [token, setToken] = useState('')
  const { setAdminToken } = useAdminStore()

  const handleLogin = (e: any) => {
    e.preventDefault()
    if (token.trim()) {
      setAdminToken(token.trim())
      window.location.reload()
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-zinc-950 text-zinc-50 font-sans p-4 selection:bg-orange-500/30">
      <Card className="w-full max-w-md bg-zinc-900/50 backdrop-blur-xl border-zinc-800 shadow-2xl">
        <CardHeader className="text-center pb-6 pt-8">
          <div className="mx-auto bg-zinc-950 w-16 h-16 rounded-2xl border border-zinc-800 flex items-center justify-center mb-6 shadow-sm">
            <Server className="w-8 h-8 text-orange-500 drop-shadow-md" />
          </div>
          <CardTitle className="text-2xl font-bold tracking-tight text-zinc-100">Rivex Admin</CardTitle>
          <CardDescription className="text-zinc-400 mt-2">Enter your admin token to securely connect</CardDescription>
        </CardHeader>
        <CardContent className="pb-8">
          <form onSubmit={handleLogin} className="space-y-4">
            <Input 
              type="password" 
              placeholder="••••••••••••" 
              required
              value={token}
              onChange={e => setToken(e.target.value)}
              className="bg-zinc-950 border-zinc-800 text-center font-mono h-12 text-lg text-zinc-200 focus-visible:ring-orange-500"
            />
            <Button type="submit" className="w-full bg-orange-500 hover:bg-orange-600 text-white h-12 font-medium shadow-lg shadow-orange-500/20 border-0">
              Sign In
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
