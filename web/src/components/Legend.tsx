import { useMemo } from 'react'

import type { GraphNode, TypeColorMap } from '../types/graph'

type LegendProps = {
  nodes: GraphNode[]
  typeColors: TypeColorMap
  activeType: string | null
  onSelectType: (type: string | null) => void
}

export function Legend({ nodes, typeColors, activeType, onSelectType }: LegendProps) {
  const typeCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const node of nodes) {
      counts.set(node.group, (counts.get(node.group) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [nodes])

  if (!typeCounts.length) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-700 bg-slate-950/60 px-3 py-2">
      {typeCounts.map(([type, count]) => {
        const color = typeColors[type] ?? { background: '#64748b', border: '#475569', font: '#fff' }
        const isActive = activeType === type
        return (
          <button
            key={type}
            onClick={() => onSelectType(isActive ? null : type)}
            className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] transition ${
              isActive
                ? 'border-amber-400 bg-amber-400/10 text-amber-100'
                : 'border-slate-700 bg-slate-800/60 text-slate-300 hover:border-slate-500'
            }`}
            title={`${count} ${type} node${count === 1 ? '' : 's'} — click to ${isActive ? 'clear' : 'highlight'}`}
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: color.background, border: `1px solid ${color.border}` }}
            />
            <span>{type}</span>
            <span className="text-slate-500">{count}</span>
          </button>
        )
      })}
    </div>
  )
}
