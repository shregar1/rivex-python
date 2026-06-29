import { executeAction } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card'
import { Button } from './ui/button'
import { useToast } from '../hooks/use-toast'

export function Actions({ actions }: { actions: any[] }) {
  const { toast } = useToast()

  const handleAction = async (name: string, dangerous: boolean) => {
    if (dangerous && !window.confirm('Are you sure you want to run this dangerous action?')) {
      return
    }

    try {
      const res = await executeAction(name)
      toast({
        title: res.ok ? 'Success' : 'Error',
        description: res.message,
        variant: res.ok ? 'default' : 'destructive',
      })
    } catch (err: any) {
      toast({
        title: 'Error',
        description: err.message,
        variant: 'destructive',
      })
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-100">Operational actions</h2>
        <p className="text-sm text-zinc-400 mt-1">One-click operational actions.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {actions.map(action => (
          <Card key={action.name} className="bg-zinc-950 border-zinc-800 text-zinc-50 shadow-sm">
            <CardHeader>
              <CardTitle className="text-lg text-zinc-100">{action.title}</CardTitle>
              <CardDescription className="text-zinc-400">{action.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button 
                variant={action.dangerous ? 'destructive' : 'secondary'}
                className={action.dangerous ? '' : 'bg-zinc-800 text-zinc-50 hover:bg-zinc-700'}
                onClick={() => handleAction(action.name, action.dangerous)}
              >
                Run Action
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
