import { useQuery } from '@tanstack/react-query'
import { fetchPartial } from '../api'
import { Card, CardContent } from './ui/card'
import { Table, TableBody, TableCell, TableRow } from './ui/table'

export function Config() {
  const { data, isLoading } = useQuery({
    queryKey: ['partial', 'config'],
    queryFn: () => fetchPartial('config')
  })

  if (isLoading) return <div>Loading...</div>

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-100">Configuration</h2>
        <p className="text-sm text-zinc-400 mt-1">Active settings (secrets redacted).</p>
      </div>
      <Card className="bg-zinc-950 border-zinc-800 text-zinc-50">
        <CardContent className="p-0 max-h-[600px] overflow-y-auto">
          <Table>
            <TableBody>
              {data && data.map((row: any) => (
                <TableRow key={row.key} className="border-zinc-800 hover:bg-zinc-900/50">
                  <TableCell className="font-medium text-zinc-400 w-1/3 break-all border-r border-zinc-800/50">{row.key}</TableCell>
                  <TableCell className="font-mono text-sm break-all">{row.value}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
