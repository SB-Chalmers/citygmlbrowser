export type LayoutMode = 'hierarchical' | 'force'

export type NodeColor = {
  background: string
  border: string
  highlight?: { background: string; border: string }
  hover?: { background: string; border: string }
}

export type GraphNode = {
  id: number
  label: string
  _baseLabel?: string
  group: string
  color?: NodeColor
  size?: number
  shape?: string
  font?: Record<string, unknown>
  details?: Record<string, unknown>
  provenance?: Record<string, string>
  children?: number[]
  hidden?: boolean
  borderWidth?: number
  title?: string
}

export type GraphEdge = {
  id?: number | string
  from: number
  to: number
  label?: string
  _label?: string
  title?: string
  arrows?: string
  dashes?: boolean
  color?: Record<string, unknown>
  font?: Record<string, unknown>
  smooth?: Record<string, unknown>
  hidden?: boolean
}

export type TypeColorMap = Record<string, { background: string; border: string; font: string }>

export type GraphPayload = {
  file: string
  dialect: {
    citygml: string | null
    energyAde: string | null
    lcaAde: string | null
  }
  graph: {
    nodes: GraphNode[]
    edges: GraphEdge[]
  }
  typeColors: TypeColorMap
}

export type ApiSuccess<T> = {
  status: 'success'
  data: T
  meta: {
    apiVersion: string
    processingMs?: number
    nodeCount?: number
    edgeCount?: number
  }
}

export type ApiErrorResponse = {
  status: 'error'
  error: {
    code: string
    message: string
    requestId?: string
  }
}
