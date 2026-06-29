import { useQuery } from '@tanstack/react-query'
import { fetchPartial } from '../api'
import { Card, CardContent } from './ui/card'
import { Table, TableBody, TableCell, TableRow } from './ui/table'

export function Setup() {
  const { data, isLoading } = useQuery({
    queryKey: ['partial', 'setup'],
    queryFn: () => fetchPartial('setup')
  })

  if (isLoading) return <div>Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-100">No admin user configured</h2>
        <p className="text-sm text-zinc-400 mt-1">Mint the first admin user.</p>
      </div>
      <Card className="bg-zinc-950 border-zinc-800 text-zinc-50">
        <CardContent className="p-0">
          <Table>
            <TableBody>
              {data && Object.entries(data).map(([key, value]: [string, any]) => (
                <TableRow key={key} className="border-zinc-800 hover:bg-zinc-900/50">
                  <TableCell className="font-medium text-zinc-400 capitalize w-1/3 border-r border-zinc-800/50">{key.replace('_', ' ')}</TableCell>
                  <TableCell className="font-mono text-sm break-all">{String(value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="bg-zinc-900/50 rounded-lg p-6 border border-zinc-800 font-mono text-sm text-zinc-300">
        <p className="text-zinc-500 mb-2"># From your project root:</p>
        <p className="text-zinc-100 mb-6">rivex createsuperuser</p>

        <p className="text-zinc-500 mb-2"># Or non-interactive (auto-generates a 256-bit token):</p>
        <p className="text-zinc-100 mb-6">rivex admin mint --username admin</p>

        <p className="text-zinc-500 mb-2"># Or set a single static token (back-compat):</p>
        <p className="text-zinc-100">#   Rivex(admin_url='/admin', admin_token='...')</p>
      </div>
    </div>
  )
}
