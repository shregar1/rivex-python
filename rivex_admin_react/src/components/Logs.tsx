import { useQuery } from '@tanstack/react-query'
import { fetchPartial } from '../api'

export function Logs() {
  const { data, isLoading } = useQuery({
    queryKey: ['partial', 'logs'],
    queryFn: () => fetchPartial('logs'),
    refetchInterval: 5000
  })

  if (isLoading) return <div>Loading...</div>

  return (
    <div className="space-y-6 flex flex-col h-full">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-100">Logs</h2>
        <p className="text-sm text-zinc-400 mt-1">Tail of the structured log file.</p>
      </div>
      <div className="bg-[#0c0c0c] rounded-lg p-4 border border-zinc-800 font-mono text-xs text-zinc-300 overflow-y-auto h-[600px] shadow-inner">
        {data?.error ? (
           <p className="text-red-400">{data.error}</p>
        ) : (
           data?.lines?.map((line: string, i: number) => (
             <div key={i} className="whitespace-pre-wrap mb-1">{line}</div>
           ))
        )}
      </div>
    </div>
  )
}
