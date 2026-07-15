import type { GraphNode, TypeColorMap } from '../types/graph'

type Dialect = {
  citygml: string | null
  energyAde: string | null
  lcaAde: string | null
}

type NodeDetailsPanelProps = {
  node: GraphNode | null
  typeColors: TypeColorMap
  dialect?: Dialect | null
}

// Provenance category → visual style + header label.
// Colours echo the LCA ADE UML palette (cyan CityGML, orange Energy ADE,
// green LCA ADE, amber linked database).
type Category = 'citygml' | 'energy' | 'lca' | 'database'

const CATEGORY_ORDER: Category[] = ['citygml', 'energy', 'lca', 'database']

const CATEGORY_STYLE: Record<Category, { label: string; accent: string; tint: string }> = {
  citygml:  { label: 'CityGML',         accent: '#38bdf8', tint: 'rgba(56,189,248,0.10)' },
  energy:   { label: 'Energy ADE',      accent: '#fb923c', tint: 'rgba(251,146,60,0.10)' },
  lca:      { label: 'LCA ADE',         accent: '#4ade80', tint: 'rgba(74,222,128,0.10)' },
  database: { label: 'Linked Database', accent: '#fcd34d', tint: 'rgba(252,211,77,0.10)' },
}

function categoryHeader(category: Category, dialect?: Dialect | null): string {
  const base = CATEGORY_STYLE[category].label
  if (!dialect) return base
  if (category === 'citygml' && dialect.citygml) return `${base} ${dialect.citygml}`
  if (category === 'energy' && dialect.energyAde && dialect.energyAde !== 'none') {
    return `${base} ${dialect.energyAde}`
  }
  if (category === 'lca' && dialect.lcaAde && dialect.lcaAde !== 'none') {
    return `${base} ${dialect.lcaAde}`
  }
  return base
}

export function NodeDetailsPanel({ node, typeColors, dialect }: NodeDetailsPanelProps) {
  if (!node) {
    return (
      <div className="text-sm text-slate-400">
        Click a node to inspect its properties.
      </div>
    )
  }

  const details = node.details ?? {}
  const provenance = node.provenance ?? {}
  const color = typeColors[node.group] ?? {
    background: '#64748b',
    border: '#475569',
    font: '#ffffff',
  }

  // Bucket the visible properties by their provenance category.
  const buckets: Record<Category, Array<[string, unknown]>> = {
    citygml: [],
    energy: [],
    lca: [],
    database: [],
  }
  for (const [key, value] of Object.entries(details)) {
    if (value === null || value === undefined || value === '') continue
    const cat = (provenance[key] as Category) ?? 'citygml'
    buckets[cat].push([key, value])
  }

  const activeCategories = CATEGORY_ORDER.filter((c) => buckets[c].length > 0)

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

      {activeCategories.length === 0 ? (
        <div className="text-xs text-slate-400">No properties.</div>
      ) : (
        <div className="max-h-[60vh] space-y-3 overflow-auto pr-1">
          {activeCategories.map((category) => {
            const style = CATEGORY_STYLE[category]
            return (
              <section
                key={category}
                className="overflow-hidden rounded-md border"
                style={{ borderColor: style.accent }}
              >
                <div
                  className="flex items-center gap-2 px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-slate-100"
                  style={{ backgroundColor: style.tint, borderBottom: `1px solid ${style.accent}` }}
                >
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: style.accent }}
                  />
                  {categoryHeader(category, dialect)}
                  <span className="ml-auto font-mono text-[10px] font-normal text-slate-400">
                    {buckets[category].length}
                  </span>
                </div>
                <table className="w-full text-left text-xs">
                  <tbody>
                    {buckets[category].map(([key, value]) => (
                      <tr key={key} className="odd:bg-slate-900 even:bg-slate-800">
                        <td className="w-[42%] border-b border-slate-700 px-2 py-1 text-slate-300">
                          {key}
                        </td>
                        <td className="border-b border-slate-700 px-2 py-1 font-mono text-[11px] text-slate-100">
                          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
