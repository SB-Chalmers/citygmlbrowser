import type { ChangeEvent } from 'react'

type UploadPanelProps = {
  onUpload: (file: File) => Promise<void>
  loading: boolean
}

export function UploadPanel({ onUpload, loading }: UploadPanelProps) {
  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    await onUpload(file)
    event.target.value = ''
  }

  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-slate-500 bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700">
      <input
        type="file"
        accept=".gml,.xml"
        className="hidden"
        onChange={handleChange}
        disabled={loading}
      />
      <span>{loading ? 'Parsing...' : 'Open CityGML File'}</span>
    </label>
  )
}
