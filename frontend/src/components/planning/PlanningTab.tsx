import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { PlanningTask, PlanningSheet, PlanningVersion } from '../../types'

const SHEETS: { id: PlanningSheet; label: string }[] = [
  { id: 'master', label: 'Master' },
  { id: 'sw', label: 'SW Schedule' },
  { id: 'peru', label: 'Peru' },
  { id: 'opl', label: 'OPL' },
]

const STATUS_COLORS: Record<string, string> = {
  green: '#16a34a', yellow: '#d97706', red: '#dc2626', grey: '#9ca3af',
}

export default function PlanningTab() {
  const [sheet, setSheet] = useState<PlanningSheet>('master')
  const [tasks, setTasks] = useState<PlanningTask[]>([])
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [versions, setVersions] = useState<PlanningVersion[]>([])
  const [loading, setLoading] = useState(false)
  const [showVersions, setShowVersions] = useState(false)
  const [msg, setMsg] = useState('')

  const load = async (s: PlanningSheet) => {
    setLoading(true); setMsg('')
    try {
      const res = await api.planning.get(s)
      setTasks(res.tasks)
      setSavedAt(res.saved_at)
    } finally { setLoading(false) }
  }

  const loadVersions = async () => {
    const res = await api.planning.versions(sheet)
    setVersions(res.versions)
  }

  useEffect(() => { load(sheet) }, [sheet])

  const restoreVersion = async (v: PlanningVersion) => {
    const res = await api.planning.getVersion(v.version_id, sheet)
    setTasks(res.tasks)
    setMsg(`Restored version from ${v.saved_at} (${v.label || 'no label'}) — not yet saved`)
    setShowVersions(false)
  }

  const reset = async () => {
    if (!confirm('Reset to Excel source? Current edits will be lost.')) return
    await api.planning.reset(sheet)
    load(sheet)
  }

  // Build gantt row indent by outline_level
  const indent = (level: number) => level * 16

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 15, fontWeight: 700 }}>Planning</h2>
        <div style={{ display: 'flex', gap: 2, background: '#f3f4f6', borderRadius: 6, padding: 2 }}>
          {SHEETS.map(s => (
            <button key={s.id} onClick={() => setSheet(s.id)} style={{
              padding: '4px 14px', borderRadius: 4, border: 'none',
              background: sheet === s.id ? 'white' : 'transparent',
              fontWeight: sheet === s.id ? 700 : 400, fontSize: 13,
              boxShadow: sheet === s.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            }}>{s.label}</button>
          ))}
        </div>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {tasks.length} tasks{savedAt ? ` · saved ${savedAt.slice(0, 16)}` : ' · from Excel'}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn-ghost" onClick={() => { setShowVersions(!showVersions); loadVersions() }}>
            {showVersions ? 'Hide' : 'Versions'}
          </button>
          <button className="btn-ghost" onClick={reset}>↺ Reset to Excel</button>
        </div>
      </div>

      {msg && <div style={{ padding: '8px 12px', background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 6, fontSize: 13 }}>{msg}</div>}

      {/* Versions panel */}
      {showVersions && (
        <div className="card" style={{ padding: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8 }}>Saved Versions ({versions.length})</div>
          {versions.length === 0 && <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No versions saved yet</div>}
          {versions.map(v => (
            <div key={v.version_id} style={{ display: 'flex', gap: 12, padding: '6px 0', borderBottom: '1px solid #f0f0f0', alignItems: 'center' }}>
              <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)', minWidth: 160 }}>{v.saved_at.slice(0, 16)}</span>
              <span style={{ flex: 1, fontSize: 13 }}>{v.label || v.diff_summary || '—'}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{v.task_count} tasks</span>
              <button className="btn-ghost" style={{ fontSize: 12, padding: '3px 10px' }} onClick={() => restoreVersion(v)}>Restore</button>
            </div>
          ))}
        </div>
      )}

      {/* Task table */}
      <div className="card" style={{ overflow: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ width: 40 }}>%</th>
              <th>Task Name</th>
              <th style={{ width: 100 }}>Start</th>
              <th style={{ width: 100 }}>Finish</th>
              <th style={{ width: 70 }}>Duration</th>
              <th style={{ width: 80 }}>Resource</th>
              <th style={{ width: 70 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>Loading…</td></tr>}
            {tasks.map(t => (
              <tr key={t.id} style={{ opacity: t.active === false ? 0.5 : 1 }}>
                <td style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
                  {t.percent_complete}%
                </td>
                <td>
                  <div style={{ paddingLeft: indent(t.outline_level ?? 0), display: 'flex', alignItems: 'center', gap: 6 }}>
                    {t.milestone && <span title="Milestone">◆</span>}
                    <span style={{
                      fontWeight: t.outline_level === 0 ? 700 : t.outline_level === 1 ? 600 : 400,
                      fontSize: t.outline_level === 0 ? 14 : 13,
                    }}>{t.task_name}</span>
                  </div>
                </td>
                <td style={{ fontSize: 12 }}>{t.start_date || '—'}</td>
                <td style={{ fontSize: 12 }}>{t.finish_date || '—'}</td>
                <td style={{ fontSize: 12, textAlign: 'center' }}>{t.duration}d</td>
                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.resource_names || '—'}</td>
                <td>
                  <span style={{
                    display: 'inline-block', width: 10, height: 10, borderRadius: 2,
                    background: STATUS_COLORS[t.status] ?? '#9ca3af', marginRight: 4,
                  }} />
                  <span style={{ fontSize: 11 }}>{t.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
