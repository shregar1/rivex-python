import { useAdminStore } from '../store'
import { Server, Activity, Settings, Wrench, FileText, Play, Code, LogOut } from 'lucide-react'

export function Sidebar({ meta }: { meta: any }) {
  const { activeTab, setActiveTab, adminToken, setAdminToken } = useAdminStore()
  
  const iconMap: Record<string, any> = {
    '◉': Server,
    '▣': Activity,
    '⚙': Settings,
    '+': Wrench,
    '≣': FileText,
    '▶': Play,
    'code': Code
  }

  const tabs = meta?.partials || []

  return (
    <aside className="w-64 flex flex-col bg-zinc-950 border-r border-zinc-900 h-full p-4">
      <div className="mb-8 px-2">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">{meta?.app_name || 'Rivex Admin'}</h1>
        <p className="text-xs text-zinc-500 mt-1 uppercase tracking-wider">{meta?.powered_by || 'Rivex'} {meta?.version || '0.0.0'}</p>
      </div>

      <nav className="flex-1 space-y-1">
        {tabs.map((tab: any) => {
          const Icon = iconMap[tab.icon] || Server
          const isActive = activeTab === tab.name
          return (
            <button
              key={tab.name}
              onClick={() => setActiveTab(tab.name)}
              className={`w-full flex items-center gap-3 px-3 py-2 text-sm rounded-md transition-colors ${
                isActive ? 'bg-zinc-800 text-zinc-50 font-medium' : 'text-zinc-400 hover:text-zinc-50 hover:bg-zinc-900/50'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-orange-500' : 'text-zinc-500'}`} />
              {tab.title}
            </button>
          )
        })}
      </nav>

      {adminToken && (
        <div className="mt-auto pt-4 border-t border-zinc-900">
           <button
             onClick={() => setAdminToken(null)}
             className="w-full flex items-center gap-3 px-3 py-2 text-sm text-zinc-400 hover:text-zinc-50 rounded-md hover:bg-zinc-900/50 transition-colors"
           >
             <LogOut className="w-4 h-4 text-zinc-500" />
             Sign Out
           </button>
        </div>
      )}
    </aside>
  )
}
