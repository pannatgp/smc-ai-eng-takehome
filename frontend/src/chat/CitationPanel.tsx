import type { Citations } from '../api/types'

export function CitationPanel({ citations }: { citations: Citations | null | undefined }) {
  if (!citations || (citations.sql.length === 0 && citations.vector.length === 0)) return null

  return (
    <details className="citation-panel">
      <summary>Sources ({citations.sql.length + citations.vector.length})</summary>

      {citations.sql.length > 0 && (
        <table className="citation-table">
          <thead>
            <tr>
              <th>Company</th>
              <th>Year</th>
              <th>Revenue</th>
              <th>Gross Profit</th>
              <th>Operating Income</th>
              <th>Net Income</th>
            </tr>
          </thead>
          <tbody>
            {citations.sql.map((row) => (
              <tr key={`${row.company}-${row.year}`}>
                <td>{row.company}</td>
                <td>{row.year}</td>
                <td>{formatUsd(row.revenue)}</td>
                <td>{formatUsd(row.gross_profit)}</td>
                <td>{formatUsd(row.operating_income)}</td>
                <td>{formatUsd(row.net_income)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {citations.vector.length > 0 && (
        <ul className="citation-chips">
          {citations.vector.map((match, i) => (
            <li key={i} title={match.snippet}>
              {match.source}
              {match.page != null ? ` — p.${match.page}` : ''}
            </li>
          ))}
        </ul>
      )}
    </details>
  )
}

function formatUsd(value: number | null): string {
  if (value == null) return '—'
  return `$${(value / 1_000_000_000).toFixed(2)}B`
}
