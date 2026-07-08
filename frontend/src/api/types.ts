export interface SqlCitation {
  company: string
  ticker: string
  year: number
  revenue: number | null
  gross_profit: number | null
  operating_income: number | null
  net_income: number | null
}

export interface VectorCitation {
  source: string
  page: number | null
  page_label: string | null
  snippet: string
}

export interface Citations {
  sql: SqlCitation[]
  vector: VectorCitation[]
}

export interface ChatResponse {
  answer: string
  citations: Citations
}

export interface MessageOut {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citations | null
  created_at: string
}
