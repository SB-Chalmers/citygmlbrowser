import { useEffect, useMemo, useRef } from 'react'
import { DataSet } from 'vis-data'
import { Network, type Options } from 'vis-network'

import type { GraphEdge, GraphNode, LayoutMode } from '../types/graph'

type GraphCanvasProps = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  layout: LayoutMode
  edgeLabels: boolean
  searchQuery: string
  fitSignal: number
  collapseAllSignal: number
  expandAllSignal: number
  onSelectNode: (node: GraphNode | null) => void
  onRenderError?: (message: string) => void
}

export function GraphCanvas({
  nodes,
  edges,
  layout,
  edgeLabels,
  searchQuery,
  fitSignal,
  collapseAllSignal,
  expandAllSignal,
  onSelectNode,
  onRenderError,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const networkRef = useRef<Network | null>(null)
  const nodesRef = useRef<DataSet<any> | null>(null)
  const edgesRef = useRef<DataSet<any> | null>(null)
  const collapsedMapRef = useRef<Map<number, Set<number>>>(new Map())
  const allEdgesRef = useRef<GraphEdge[]>([])
  const searchQueryRef = useRef<string>('')

  // Shared "spotlight": dim everything except the given node ids (and edges between them).
  // Passing null clears the spotlight and restores full opacity. Reused by both
  // the search/legend filter and the single-click downstream highlight.
  const applySpotlight = useRef((ids: Set<number> | null) => {
    const nodeSet = nodesRef.current
    const edgeSet = edgesRef.current
    if (!nodeSet || !edgeSet) return

    const DIM_NODE = 0.12
    const DIM_EDGE = 0.08

    nodeSet.update(
      nodeSet.get().map((node: any) => ({
        id: node.id,
        opacity: !ids || ids.has(node.id) ? 1 : DIM_NODE,
      })),
    )

    edgeSet.update(
      edgeSet.get().map((edge: any) => {
        const active = !ids || (ids.has(edge.from) && ids.has(edge.to))
        return {
          id: edge.id,
          color: { ...(edge.color ?? {}), opacity: active ? 1 : DIM_EDGE },
        }
      }),
    )
  })

  // Compute the spotlight set from the current search / legend query.
  // Only the matching nodes are highlighted (no downstream expansion).
  const spotlightFromSearch = useRef((query: string) => {
    const nodeSet = nodesRef.current
    if (!nodeSet) return

    const q = query.trim().toLowerCase()
    if (!q) {
      applySpotlight.current(null)
      return
    }

    const matches = new Set<number>()
    nodeSet.forEach((node: any) => {
      if (node.label.toLowerCase().includes(q) || (node.group ?? '').toLowerCase().includes(q)) {
        matches.add(node.id)
      }
    })
    applySpotlight.current(matches)
  })

  const options = useMemo<Options>(() => {
    if (layout === 'hierarchical') {
      return {
        interaction: { hover: true, tooltipDelay: 80 },
        layout: {
          hierarchical: {
            enabled: true,
            direction: 'UD',
            sortMethod: 'directed',
            nodeSpacing: 140,
            levelSeparation: 120,
            treeSpacing: 220,
          },
        },
        physics: { enabled: false },
        nodes: { borderWidth: 2, borderWidthSelected: 3 },
        edges: { width: 1.4, selectionWidth: 3 },
      }
    }

    return {
      interaction: { hover: true, tooltipDelay: 80 },
      layout: { hierarchical: { enabled: false }, randomSeed: 42 },
      physics: {
        enabled: true,
        solver: 'barnesHut',
        barnesHut: {
          gravitationalConstant: -8000,
          springLength: 150,
          springConstant: 0.04,
          damping: 0.2,
          avoidOverlap: 0.6,
        },
        stabilization: { enabled: false },
      },
      nodes: { borderWidth: 2, borderWidthSelected: 3 },
      edges: { width: 1.4, selectionWidth: 3 },
    }
  }, [layout])

  useEffect(() => {
    if (!containerRef.current) return

    const networkNodes = new DataSet<any>(
      nodes.map((node) => ({
        ...node,
        _baseLabel: node._baseLabel ?? node.label,
        hidden: false,
      })),
    )
    const networkEdges = new DataSet<any>(
      edges.map((edge, index) => ({
        ...edge,
        id: edge.id ?? `${edge.from}-${edge.to}-${index}`,
        label: edgeLabels ? edge._label ?? '' : '',
        hidden: false,
      })),
    )

    allEdgesRef.current = edges
    collapsedMapRef.current.clear()

    let network: Network
    try {
      network = new Network(containerRef.current, { nodes: networkNodes, edges: networkEdges }, options)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown graph renderer error'
      onRenderError?.(`Graph renderer failed to initialize: ${message}`)
      return
    }

    network.on('click', (params) => {
      if (!params.nodes.length) {
        onSelectNode(null)
        // Empty-space click: restore whatever the search/legend filter dictates.
        spotlightFromSearch.current(searchQueryRef.current)
        return
      }
      const clickedId = params.nodes[0] as number
      const selected = networkNodes.get(clickedId) as GraphNode | null
      onSelectNode(selected ?? null)

      // Spotlight the clicked node plus all downstream (descendant) nodes.
      const downstream = getDescendants(clickedId, networkNodes)
      downstream.add(clickedId)
      applySpotlight.current(downstream)
      network.unselectAll()
    })

    network.on('doubleClick', (params) => {
      if (!params.nodes.length) return
      toggleCollapse(params.nodes[0], networkNodes, networkEdges, collapsedMapRef.current)
      network.unselectAll()
    })

    nodesRef.current = networkNodes
    edgesRef.current = networkEdges
    networkRef.current = network

    network.fit()
    setTimeout(() => {
      try {
        network.fit()
      } catch {
        onRenderError?.('Graph renderer failed during viewport fit')
      }
    }, 50)

    return () => {
      network.destroy()
      networkRef.current = null
    }
  }, [nodes, edges, layout, options, edgeLabels, onSelectNode])

  useEffect(() => {
    const edgeSet = edgesRef.current
    if (!edgeSet) return
    edgeSet.update(edgeSet.get().map((edge) => ({ id: edge.id, label: edgeLabels ? edge._label ?? '' : '' })))
  }, [edgeLabels])

  useEffect(() => {
    searchQueryRef.current = searchQuery
    spotlightFromSearch.current(searchQuery)
  }, [searchQuery])

  useEffect(() => {
    networkRef.current?.fit()
  }, [fitSignal])

  useEffect(() => {
    const nodeSet = nodesRef.current
    const edgeSet = edgesRef.current
    if (!nodeSet || !edgeSet) return

    const order = bfsOrder(nodeSet, allEdgesRef.current)
    for (let index = order.length - 1; index >= 0; index -= 1) {
      const nodeId = order[index]
      const node = nodeSet.get(nodeId)
      if (!node || !node.children?.length || collapsedMapRef.current.has(nodeId)) continue
      toggleCollapse(nodeId, nodeSet, edgeSet, collapsedMapRef.current)
    }
  }, [collapseAllSignal])

  useEffect(() => {
    const nodeSet = nodesRef.current
    const edgeSet = edgesRef.current
    if (!nodeSet || !edgeSet) return

    const order = bfsOrder(nodeSet, allEdgesRef.current)
    for (const id of order) {
      if (collapsedMapRef.current.has(id)) {
        toggleCollapse(id, nodeSet, edgeSet, collapsedMapRef.current)
      }
    }
  }, [expandAllSignal])

  return <div ref={containerRef} className="h-full w-full" style={{ height: '100%', minHeight: 0 }} />
}

function bfsOrder(nodeSet: DataSet<any>, allEdges: GraphEdge[]): number[] {
  const roots: number[] = []
  const order: number[] = []

  nodeSet.forEach((node) => {
    const hasParent = allEdges.some((edge) => edge.to === node.id)
    if (!hasParent) roots.push(node.id)
  })

  const queue = [...roots]
  const visited = new Set(queue)

  while (queue.length) {
    const id = queue.shift()
    if (id === undefined) continue

    order.push(id)
    const node = nodeSet.get(id)
    if (!node) continue

    for (const childId of node.children ?? []) {
      if (!visited.has(childId)) {
        visited.add(childId)
        queue.push(childId)
      }
    }
  }

  return order
}

function getDescendants(nodeId: number, nodeSet: DataSet<any>, visited = new Set<number>()): Set<number> {
  const node = nodeSet.get(nodeId)
  if (!node) return visited

  for (const child of node.children ?? []) {
    if (!visited.has(child)) {
      visited.add(child)
      getDescendants(child, nodeSet, visited)
    }
  }

  return visited
}

function toggleCollapse(
  nodeId: number,
  nodeSet: DataSet<any>,
  edgeSet: DataSet<any>,
  collapsedMap: Map<number, Set<number>>,
): void {
  const node = nodeSet.get(nodeId)
  if (!node || !node.children?.length) return

  if (collapsedMap.has(nodeId)) {
    const hidden = collapsedMap.get(nodeId)
    if (!hidden) return
    collapsedMap.delete(nodeId)

    hidden.forEach((id) => {
      const stillHidden = [...collapsedMap.values()].some((set) => set.has(id))
      if (!stillHidden) {
        const childNode = nodeSet.get(id)
        nodeSet.update({ id, hidden: false, label: childNode?._baseLabel ?? childNode?.label ?? '' })
      }
    })

    edgeSet.forEach((edge) => {
      if (!hidden.has(edge.from) && !hidden.has(edge.to)) return
      const fromStillHidden = [...collapsedMap.values()].some((set) => set.has(edge.from))
      const toStillHidden = [...collapsedMap.values()].some((set) => set.has(edge.to))
      if (!fromStillHidden && !toStillHidden) {
        edgeSet.update({ id: edge.id, hidden: false })
      }
    })

    nodeSet.update({ id: nodeId, label: node._baseLabel ?? node.label })
    return
  }

  const descendants = getDescendants(nodeId, nodeSet)
  collapsedMap.set(nodeId, descendants)

  descendants.forEach((id) => {
    nodeSet.update({ id, hidden: true })
  })

  edgeSet.forEach((edge) => {
    if (descendants.has(edge.from) || descendants.has(edge.to)) {
      edgeSet.update({ id: edge.id, hidden: true })
    }
  })

  const count = descendants.size
  nodeSet.update({ id: nodeId, label: `${node._baseLabel ?? node.label}\n(+${count})` })
}

