import { useState, type ChangeEvent } from 'react'

type UploadPanelProps = {
  onUpload: (file: File) => Promise<void>
  loading: boolean
}

export function UploadPanel({ onUpload, loading }: UploadPanelProps) {
  const demoFiles = [
    { label: 'Alderaan LCA Example', path: `${import.meta.env.BASE_URL}demos/alderaan-lca.gml`, fileName: 'Alderaan-LCA.gml' },
    { label: 'FZK Haus LCA Example', path: `${import.meta.env.BASE_URL}demos/fzk-haus-lca.gml`, fileName: 'FZKHouseLoD3-LCA.gml' },
  ] as const

  const [selectedDemoPath, setSelectedDemoPath] = useState<string>(demoFiles[1].path)

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    await onUpload(file)
    event.target.value = ''
  }

  async function handleOpenDemo() {
    const selectedDemo = demoFiles.find((demo) => demo.path === selectedDemoPath)
    if (!selectedDemo) return

    const response = await fetch(selectedDemo.path)
    if (!response.ok) {
      throw new Error(`Failed to load demo file: ${selectedDemo.fileName}`)
    }

    const content = await response.text()
    const file = new File([content], selectedDemo.fileName, { type: 'application/xml' })
    await onUpload(file)
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
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

      <select
        className="rounded-md border border-slate-500 bg-slate-800 px-2 py-2 text-sm text-slate-100"
        value={selectedDemoPath}
        onChange={(event) => setSelectedDemoPath(event.target.value)}
        disabled={loading}
      >
        {demoFiles.map((demo) => (
          <option key={demo.path} value={demo.path}>
            {demo.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        className="rounded-md border border-amber-500/60 bg-amber-500/20 px-3 py-2 text-sm text-amber-200 hover:bg-amber-500/30 disabled:cursor-not-allowed disabled:opacity-60"
        onClick={handleOpenDemo}
        disabled={loading}
      >
        Open Demo
      </button>
    </div>
  )
}
