import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { OPLEntry } from '../../types'
import { StatusBadge, PriorityBadge } from '../ui/StatusBadge'

export default function BoschTab() {
  const [tasks, setTasks] = useState<OPLEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [pushingAll, setPushingAll] = useState(false)
  const [msg, setMsg] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.bosch.allTasks()
      setTasks(res.tasks)
      setTotal(res.total)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const sync = async () => {
    setSyncing(true); setMsg('')
    try {
      const r = await api.bosch.sync()
      setMsg(`Sync done: +${r.added} added, ${r.updated} updated, ${r.unchanged} unchanged`)
      load()
    } catch (e) { setMsg('Sync failed: ' + String(e)) }
    finally { setSyncing(false) }
  }

  const pushAll = async () => {
    setPushingAll(true); setMsg('')
    try {
      const r = await api.bosch.pushAll()
      setMsg(`Push done: ${r.pushed} pushed, ${r.failed} failed`)
      load()
    } catch (e) { setMsg('Push failed: ' + String(e)) }
    finally { setPushingAll(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>Bosch OPL Tasks</h2>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{total} total</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn-ghost" onClick={sync} disabled={syncing}>
            {syncing ? 'Syncing…' : '↓ Sync from Bosch'}
          </button>
          <button className="btn-ghost" onClick={pushAll} disabled={pushingAll}>
            {pushingAll ? 'Pushing…' : '↑ Push All Local'}
          </button>
        </div>
      </div>
      {msg && <div style={{ padding: '8px 12px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6, fontSize: 13 }}>{msg}</div>}
      <div className="card" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 110 }}>ID</th>
              <th>Subject</th>
              <th style={{ width: 130 }}>Owner</th>
              <th style={{ width: 90 }}>Due</th>
              <th style={{ width: 90 }}>Priority</th>
              <th style={{ width: 100 }}>Status</th>
              <th style={{ width: 70 }}>Source</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>Loading…</td></tr>}
            {tasks.map(t => (
              <tr key={t.id}>
                <td style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)' }}>{t.id}</td>
                <td style={{ fontWeight: 500 }}>{t.subject}</td>
                <td style={{ fontSize: 13 }}>{t.owner}</td>
                <td style={{ fontSize: 12 }}>{t.due_date ?? '—'}</td>
                <td><PriorityBadge priority={t.priority} /></td>
                <td><StatusBadge status={t.status} /></td>
                <td style={{ fontSize: 11 }}>
                  <span style={{ padding: '2px 6px', borderRadius: 4, background: t.id.startsWith('BOSCH') ? '#dbeafe' : '#f0fdf4', color: t.id.startsWith('BOSCH') ? '#1d4ed8' : '#15803d' }}>
                    {t.id.startsWith('BOSCH') ? 'Bosch' : 'Local'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
