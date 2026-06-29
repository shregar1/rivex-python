import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useAdminStore } from './store'
import { fetchMeta } from './api'
import { Sidebar } from './components/Sidebar'
import { Overview } from './components/Overview'
import { Runtime } from './components/Runtime'
import { Config } from './components/Config'
import { Setup } from './components/Setup'
import { Logs } from './components/Logs'
import { Actions } from './components/Actions'
import { Generate } from './components/Generate'
import { Login } from './components/Login'

const queryClient = new QueryClient()

function Shell() {
  const { adminToken, activeTab } = useAdminStore()
  
  const { data: meta, isLoading, error } = useQuery({
    queryKey: ['meta'],
    queryFn: fetchMeta,
    retry: false
  })

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center bg-zinc-950 text-zinc-50 font-sans">Loading...</div>
  }

  if (error && (error as Error).message === '401') {
    return <Login />
  }

  if (!adminToken && meta?.has_auth) {
    return <Login />
  }

  if (!meta?.has_auth && !adminToken) {
    // Force setup tab if no auth configured
    if (activeTab !== 'setup') {
      useAdminStore.getState().setActiveTab('setup')
    }
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'overview': return <Overview />
      case 'runtime': return <Runtime />
      case 'config': return <Config />
      case 'setup': return <Setup />
      case 'logs': return <Logs />
      case 'actions': return <Actions actions={meta?.actions || []} />
      case 'generate': return <Generate />
      default: return <Overview />
    }
  }

  return (
    <div className="flex h-screen w-full bg-zinc-950 text-zinc-50 font-sans selection:bg-orange-500/30 overflow-hidden">
      <Sidebar meta={meta} />
      <main className="flex-1 overflow-y-auto bg-zinc-950 p-8 border-l border-zinc-800 relative">
         <div className="max-w-4xl mx-auto pb-24">
           {renderContent()}
         </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Shell />
    </QueryClientProvider>
  )
}
