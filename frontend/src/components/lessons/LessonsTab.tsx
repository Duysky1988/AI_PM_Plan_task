import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { LessonLearned } from '../../types'

export default function LessonsTab() {
  const [lessons, setLessons] = useState<LessonLearned[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [msg, setMsg] = useState('')
  const [search, setSearch] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.bosch.allLessons()
      setLessons(res.lessons)
      setTotal(res.total)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const sync = async () => {
    setSyncing(true); setMsg('')
    try {
      const r = await api.bosch.syncLessons()
      setMsg(`Sync done: +${r.added} added, ${r.updated} updated`)
      load()
    } catch (e) { setMsg('Sync failed: ' + String(e)) }
    finally { setSyncing(false) }
  }

  const q = search.toLowerCase()
  const filtered = q
    ? lessons.filter(l => l.subject.toLowerCase().includes(q) || l.observation.toLowerCase().includes(q))
    : lessons

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>Lessons Learned</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{total} total</span>
        <input placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200 }} />
        <div style={{ marginLeft: 'auto' }}>
          <button className="btn-ghost" onClick={sync} disabled={syncing}>
            {syncing ? 'Syncing…' : '↓ Sync Lessons'}
          </button>
        </div>
      </div>
      {msg && <div style={{ padding: '8px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6, fontSize: 13 }}>{msg}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>Loading…</div>}
        {filtered.map(l => (
          <div key={l.id} className="card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
              <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)', minWidth: 70 }}>{l.id}</span>
              <span style={{ flex: 1, fontWeight: 600 }}>{l.subject || l.observation}</span>
              <span className={`badge badge-${l.status}`}>{l.status}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, fontSize: 13 }}>
              {l.cause && <div><strong>Cause:</strong> {l.cause}</div>}
              {l.actions && <div><strong>Actions:</strong> {l.actions}</div>}
              {l.category && <div><strong>Category:</strong> {l.category} {l.subcategory ? `/ ${l.subcategory}` : ''}</div>}
              {l.phase && <div><strong>Phase:</strong> {l.phase}</div>}
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              Owner: {l.owner} · Created: {l.created_at}
            </div>
          </div>
        ))}
        {!loading && filtered.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>No lessons found</div>
        )}
      </div>
    </div>
  )
}
