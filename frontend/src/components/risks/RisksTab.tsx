import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Risk } from '../../types'

export default function RisksTab() {
  const [risks, setRisks] = useState<Risk[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [msg, setMsg] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.bosch.allRisks()
      setRisks(res.risks)
      setTotal(res.total)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const sync = async () => {
    setSyncing(true); setMsg('')
    try {
      const r = await api.bosch.syncRisks()
      setMsg(`Sync done: +${r.added} added, ${r.updated} updated`)
      load()
    } catch (e) { setMsg('Sync failed: ' + String(e)) }
    finally { setSyncing(false) }
  }

  const scoreColor = (score: number | null) => {
    if (!score) return '#9ca3af'
    if (score >= 15) return '#dc2626'
    if (score >= 8) return '#d97706'
    return '#16a34a'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>Risks</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{total} total</span>
        <div style={{ marginLeft: 'auto' }}>
          <button className="btn-ghost" onClick={sync} disabled={syncing}>
            {syncing ? 'Syncing…' : '↓ Sync Risks'}
          </button>
        </div>
      </div>
      {msg && <div style={{ padding: '8px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6, fontSize: 13 }}>{msg}</div>}
      <div className="card" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 90 }}>ID</th>
              <th>Risk Name</th>
              <th style={{ width: 100 }}>Category</th>
              <th style={{ width: 60 }}>P</th>
              <th style={{ width: 60 }}>I</th>
              <th style={{ width: 70 }}>Score</th>
              <th style={{ width: 100 }}>Status</th>
              <th style={{ width: 130 }}>Owner</th>
              <th style={{ width: 70 }}>Measures</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={9} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>Loading…</td></tr>}
            {risks.map(r => (
              <>
                <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                  <td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)' }}>{r.id}</td>
                  <td style={{ fontWeight: 500 }}>{r.subject}</td>
                  <td style={{ fontSize: 12 }}>{r.category}</td>
                  <td style={{ textAlign: 'center' }}>{r.probability ?? '—'}</td>
                  <td style={{ textAlign: 'center' }}>{r.impact ?? '—'}</td>
                  <td>
                    {r.risk_score != null
                      ? <span style={{ fontWeight: 700, color: scoreColor(r.risk_score) }}>{r.risk_score}</span>
                      : '—'}
                  </td>
                  <td>
                    <span className={`badge badge-${r.status}`}>{r.status}</span>
                  </td>
                  <td style={{ fontSize: 12 }}>{r.owner}</td>
                  <td style={{ textAlign: 'center', fontSize: 13 }}>{r.measures.length}</td>
                </tr>
                {expanded === r.id && r.measures.length > 0 && (
                  <tr key={r.id + '-measures'}>
                    <td colSpan={9} style={{ background: '#f9fafb', padding: '8px 20px 8px 40px' }}>
                      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: 'var(--text-muted)' }}>MEASURES</div>
                      {r.measures.map((m, i) => (
                        <div key={i} style={{ display: 'flex', gap: 12, padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                          <span style={{ minWidth: 180, fontWeight: 500 }}>{m.subject}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{m.owner}</span>
                          <span>{m.due_date || '—'}</span>
                          <span className={`badge badge-${m.status}`}>{m.status}</span>
                        </div>
                      ))}
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
