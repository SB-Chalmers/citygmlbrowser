import { useMemo, useState } from 'react'

import { GraphCanvas } from './components/GraphCanvas'
import { Legend } from './components/Legend'
import { NodeDetailsPanel } from './components/NodeDetailsPanel'
import { Toolbar } from './components/Toolbar'
import { UploadPanel } from './components/UploadPanel'
import { ApiError, uploadGraph } from './services/api'
import type { GraphNode, GraphPayload, LayoutMode } from './types/graph'
import { logger } from './utils/logger'

function App() {
  const [payload, setPayload] = useState<GraphPayload | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [renderError, setRenderError] = useState<string | null>(null)
  const [layout, setLayout] = useState<LayoutMode>('hierarchical')
  const [edgeLabels, setEdgeLabels] = useState(false)
  const [search, setSearch] = useState('')

  const [fitSignal, setFitSignal] = useState(0)
  const [collapseAllSignal, setCollapseAllSignal] = useState(0)
  const [expandAllSignal, setExpandAllSignal] = useState(0)

  async function handleUpload(file: File): Promise<void> {
    setLoading(true)
    setError(null)

    try {
      logger.info('upload_start', { fileName: file.name, sizeBytes: file.size })
      const response = await uploadGraph(file)
      setPayload(response.data)
      setSelectedNode(null)
      setSearch('')
      setRenderError(null)
      logger.info('upload_success', {
        fileName: response.data.file,
        nodeCount: response.meta.nodeCount,
        edgeCount: response.meta.edgeCount,
        processingMs: response.meta.processingMs,
      })
    } catch (caught) {
      const message =
        caught instanceof ApiError
          ? `${caught.message}${caught.requestId ? ` (request ${caught.requestId})` : ''}`
          : 'Upload failed unexpectedly'
      setError(message)

      logger.error('upload_failed', {
        message,
        error: caught instanceof Error ? caught.message : String(caught),
      })
    } finally {
      setLoading(false)
    }
  }

  const graphMeta = useMemo(() => {
    if (!payload) return null
    return {
      file: payload.file,
      citygml: payload.dialect.citygml ?? 'unknown',
      energyAde: payload.dialect.energyAde ?? 'none',
      nodeCount: payload.graph.nodes.length,
      edgeCount: payload.graph.edges.length,
    }
  }, [payload])

  const compatibilityWarning = useMemo(() => {
    if (!graphMeta) return null
    if (graphMeta.nodeCount > 1) return null

    return `Parsed a minimal graph (${graphMeta.nodeCount} node). This often means the file dialect is only partially supported right now (detected CityGML ${graphMeta.citygml}).`
  }, [graphMeta])

  return (
    <div className="mx-auto flex h-screen max-w-[1600px] flex-col overflow-hidden px-4 py-4 text-slate-100 md:px-6">
      <header className="mb-3 rounded-xl border border-slate-700 bg-slate-900/80 p-4 backdrop-blur">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-bold tracking-wide text-amber-400">CityGML Browser</h1>
          <UploadPanel onUpload={handleUpload} loading={loading} />
          {graphMeta ? (
            <div className="text-xs text-slate-300">
              <span className="mr-3">{graphMeta.file}</span>
              <span className="mr-3">CityGML {graphMeta.citygml}</span>
              <span className="mr-3">Energy ADE {graphMeta.energyAde}</span>
              <span>{graphMeta.nodeCount} nodes / {graphMeta.edgeCount} edges</span>
            </div>
          ) : (
            <p className="text-xs text-slate-400">Upload a .gml file to parse and browse it.</p>
          )}
        </div>
        {error ? (
          <div className="mt-3 rounded border border-rose-500/40 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        ) : null}
        {renderError ? (
          <div className="mt-3 rounded border border-rose-500/40 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
            {renderError}
          </div>
        ) : null}
        {compatibilityWarning ? (
          <div className="mt-3 rounded border border-amber-500/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">
            {compatibilityWarning}
          </div>
        ) : null}
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/80">
          <Toolbar
            layout={layout}
            edgeLabels={edgeLabels}
            search={search}
            onLayoutChange={setLayout}
            onToggleLabels={() => setEdgeLabels((prev) => !prev)}
            onFit={() => setFitSignal((prev) => prev + 1)}
            onCollapseAll={() => setCollapseAllSignal((prev) => prev + 1)}
            onExpandAll={() => setExpandAllSignal((prev) => prev + 1)}
            onSearch={setSearch}
          />

          {payload ? (
            <div className="min-h-0 flex-1">
              <GraphCanvas
              nodes={payload.graph.nodes}
              edges={payload.graph.edges}
              layout={layout}
              edgeLabels={edgeLabels}
              searchQuery={search}
              fitSignal={fitSignal}
              collapseAllSignal={collapseAllSignal}
              expandAllSignal={expandAllSignal}
              onSelectNode={setSelectedNode}
              onRenderError={(message) => {
                setRenderError(message)
                logger.error('graph_render_failed', { message })
              }}
              />
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 items-center justify-center p-6 text-center text-slate-400">
              <div>
                <p className="text-base text-slate-200">No graph loaded yet</p>
                <p className="mt-2 text-sm">Open a CityGML file to render the building graph.</p>
              </div>
            </div>
          )}
          {payload ? (
            <Legend
              nodes={payload.graph.nodes}
              typeColors={payload.typeColors}
              activeType={payload.typeColors[search] ? search : null}
              onSelectType={(type) => setSearch(type ?? '')}
            />
          ) : null}
        </section>

        <aside className="min-h-0 overflow-auto rounded-xl border border-slate-700 bg-slate-900/80 p-4">
          <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-amber-400">Properties</h2>
          <NodeDetailsPanel node={selectedNode} typeColors={payload?.typeColors ?? {}} />
        </aside>
      </main>
    </div>
  )
}

export default App
