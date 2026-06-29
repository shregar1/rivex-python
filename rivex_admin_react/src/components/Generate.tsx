import { useState } from 'react'
import { executeCodegen } from '../api'
import { Button } from './ui/button'
import { Textarea } from './ui/textarea'
import { Input } from './ui/input'
import { useToast } from '../hooks/use-toast'

export function Generate() {
  const { toast } = useToast()
  const [resource, setResource] = useState('')
  const [description, setDescription] = useState('')
  const [fields, setFields] = useState('# title: str:required:max=200\n# description: str:optional:max=2000\n# is_completed: bool:default=false')
  const [preview, setPreview] = useState<any>(null)

  const handlePreview = async (e: any) => {
    e.preventDefault()
    try {
      const res = await executeCodegen('preview', { resource, description, fields })
      if (!res.ok) {
        toast({ title: 'Error', description: res.error, variant: 'destructive' })
      } else {
        setPreview(res)
      }
    } catch (err: any) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' })
    }
  }

  const handleApply = async () => {
    if (!preview?.plan_id) return
    try {
      const res = await executeCodegen(`apply/${preview.plan_id}`)
      if (!res.ok) {
        toast({ title: 'Error', description: res.error, variant: 'destructive' })
      } else {
        toast({ title: 'Success', description: `Applied ${res.written?.length} files.` })
        setPreview(null)
      }
    } catch (err: any) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' })
    }
  }

  const handleCancel = async () => {
    if (!preview?.plan_id) return
    try {
      const res = await executeCodegen(`cancel/${preview.plan_id}`)
      setPreview(null)
      toast({ title: 'Cancelled', description: res.message })
    } catch (err: any) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-zinc-100">Generate resource</h2>
        <p className="text-sm text-zinc-400 mt-1">Type an API spec, preview the layered code, apply to the repo.</p>
      </div>

      {!preview ? (
        <form onSubmit={handlePreview} className="space-y-4 max-w-2xl">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Resource name (snake_case)</label>
            <Input required value={resource} onChange={e => setResource(e.target.value)} placeholder="items" className="bg-zinc-900 border-zinc-800 text-zinc-100" />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Description</label>
            <Input value={description} onChange={e => setDescription(e.target.value)} placeholder="Demo resource" className="bg-zinc-900 border-zinc-800 text-zinc-100" />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Field schema (one per line)</label>
            <Textarea required value={fields} onChange={e => setFields(e.target.value)} rows={10} className="bg-zinc-900 border-zinc-800 font-mono text-sm text-zinc-100" />
          </div>
          <Button type="submit" className="bg-orange-500 hover:bg-orange-600 text-white border-0 shadow-sm shadow-orange-500/20 font-medium">Generate Preview</Button>
        </form>
      ) : (
        <div className="space-y-4">
          <div className="bg-zinc-900 p-4 rounded-md border border-zinc-800 flex justify-between items-center shadow-sm">
            <div>
              <p className="font-semibold text-zinc-100">{preview.summary}</p>
              <p className="text-sm text-zinc-400">Creates: {preview.creates} | Modifies: {preview.modifies}</p>
            </div>
            <div className="space-x-3">
              <Button variant="secondary" onClick={handleCancel} className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200">Cancel</Button>
              <Button onClick={handleApply} className="bg-orange-500 hover:bg-orange-600 text-white font-medium shadow-sm shadow-orange-500/20 border-0">Apply to Disk</Button>
            </div>
          </div>
          <div className="bg-[#0c0c0c] p-4 rounded-md border border-zinc-800 font-mono text-sm overflow-x-auto whitespace-pre text-zinc-300 shadow-inner">
            {preview.preview}
          </div>
        </div>
      )}
    </div>
  )
}
