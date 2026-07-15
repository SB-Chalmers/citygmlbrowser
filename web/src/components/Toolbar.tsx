import type { LayoutMode } from '../types/graph'

type ToolbarProps = {
  layout: LayoutMode
  edgeLabels: boolean
  search: string
  onLayoutChange: (layout: LayoutMode) => void
  onToggleLabels: () => void
  onFit: () => void
  onCollapseAll: () => void
  onExpandAll: () => void
  onSearch: (value: string) => void
}

export function Toolbar({
  layout,
  edgeLabels,
  search,
  onLayoutChange,
  onToggleLabels,
  onFit,
  onCollapseAll,
  onExpandAll,
  onSearch,
}: ToolbarProps) {
  const base = 'rounded border px-2 py-1 text-xs transition'
  const inactive = 'border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-700'
  const active = 'border-amber-500 bg-amber-500 text-slate-950'

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-700 bg-slate-900 px-4 py-3">
      <button
        className={`${base} ${layout === 'hierarchical' ? active : inactive}`}
        onClick={() => onLayoutChange('hierarchical')}
      >
        Hierarchical
      </button>
      <button className={`${base} ${layout === 'force' ? active : inactive}`} onClick={() => onLayoutChange('force')}>
        Force
      </button>
      <button className={`${base} ${inactive}`} onClick={onFit}>
        Fit
      </button>
      <button className={`${base} ${inactive}`} onClick={onCollapseAll}>
        Collapse All
      </button>
      <button className={`${base} ${inactive}`} onClick={onExpandAll}>
        Expand All
      </button>
      <button className={`${base} ${edgeLabels ? active : inactive}`} onClick={onToggleLabels}>
        Edge Labels
      </button>
      <input
        className="ml-auto w-56 rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-100 outline-none focus:border-amber-500"
        placeholder="Search nodes..."
        value={search}
        onChange={(event) => onSearch(event.target.value)}
      />
    </div>
  )
}
