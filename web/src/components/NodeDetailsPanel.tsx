import type { GraphNode, TypeColorMap } from '../types/graph'

type NodeDetailsPanelProps = {
  node: GraphNode | null
  typeColors: TypeColorMap
}

export function NodeDetailsPanel({ node, typeColors }: NodeDetailsPanelProps) {
  if (!node) {
    return (
      <div className="text-sm text-slate-400">
        Click a node to inspect its properties.
      </div>
    )
  }

  const details = node.details ?? {}
  const color = typeColors[node.group] ?? {
    background: '#64748b',
    border: '#475569',
    font: '#ffffff',
  }

  return (
    <div className="space-y-3">
      <span
        className="inline-block rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide"
        style={{
          backgroundColor: color.background,
          borderColor: color.border,
          color: color.font,
        }}
      >
        {node.group}
      </span>
      <h2 className="text-sm font-semibold text-slate-100">{node.label.replaceAll('\n', ' ')}</h2>
      <div className="max-h-[55vh] overflow-auto rounded-md border border-slate-700">
        <table className="w-full text-left text-xs">
          <tbody>
            {Object.entries(details)
              .filter(([, value]) => value !== null && value !== undefined && value !== '')
              .map(([key, value]) => (
                <tr key={key} className="odd:bg-slate-900 even:bg-slate-800">
                  <td className="w-[42%] border-b border-slate-700 px-2 py-1 text-slate-300">{key}</td>
                  <td className="border-b border-slate-700 px-2 py-1 font-mono text-[11px] text-slate-100">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
