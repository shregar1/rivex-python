import { useQuery } from '@tanstack/react-query'
import { fetchPartial } from '../api'
import { Card, CardContent } from './ui/card'
import { Table, TableBody, TableCell, TableRow } from './ui/table'

export function Overview() {
  const { data, isLoading } = useQuery({
    queryKey: ['partial', 'overview'],
    queryFn: () => fetchPartial('overview')
  })

  if (isLoading) return <div>Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-100">Service identity</h2>
        <p className="text-sm text-zinc-400 mt-1">Service identity and environment.</p>
      </div>
      <Card className="bg-zinc-950 border-zinc-800 text-zinc-50">
        <CardContent className="p-0">
          <Table>
            <TableBody>
              {data && Object.entries(data).map(([key, value]: [string, any]) => (
                <TableRow key={key} className="border-zinc-800 hover:bg-zinc-900/50">
                  <TableCell className="font-medium text-zinc-400 capitalize w-1/3 border-r border-zinc-800/50">{key}</TableCell>
                  <TableCell className="font-mono text-sm">{String(value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
