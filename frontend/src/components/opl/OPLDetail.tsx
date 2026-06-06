import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { OPLEntry, OPLStatus } from '../../types'
import { StatusBadge, PriorityBadge } from '../ui/StatusBadge'

const STATUSES: OPLStatus[] = ['running', 'closed', 'on_hold', 'waiting_approval', 'draft', 'rejected', 'deleted']

interface Props { id: string; onClose: () => void }

export default function OPLDetail({ id, onClose }: Props) {
  const [entry, setEntry] = useState<(OPLEntry & { subtasks: OPLEntry[] }) | null>(null)
  const [loading, setLoading] = useState(true)
  const [note, setNote] = useState('')
  const [newStatus, setNewStatus] = useState<OPLStatus | ''>('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.opl.get(id).then(e => { setEntry(e); setLoading(false) })
  }, [id])

  const addNote = async () => {
    if (!note.trim() || !entry) return
    setSaving(true)
    await api.opl.setStatus(id, entry.status, note)
    const updated = await api.opl.get(id)
    setEntry(updated)
    setNote('')
    setSaving(false)
  }

  const changeStatus = async () => {
    if (!newStatus || !entry) return
    setSaving(true)
    await api.opl.setStatus(id, newStatus)
    const updated = await api.opl.get(id)
    setEntry(updated)
    setNewStatus('')
    setSaving(false)
  }

  const togglePin = async () => {
    if (!entry) return
    await api.opl.update(id, { pinned: !entry.pinned })
    setEntry({ ...entry, pinned: !entry.pinned })
  }

  if (loading) return <Overlay onClose={onClose}><div style={{ padding: 40, textAlign: 'center' }}>Loading…</div></Overlay>
  if (!entry) return null

  return (
    <Overlay onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0 }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace', marginBottom: 4 }}>{entry.id}</div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>{entry.subject || '(no subject)'}</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <StatusBadge status={entry.status} />
              <PriorityBadge priority={entry.priority} />
              <span className="badge" style={{ background: '#f3f4f6', color: '#374151' }}>{entry.entry_type}</span>
              {entry.pinned && <span className="badge" style={{ background: '#fef9c3', color: '#854d0e' }}>📌 Pinned</span>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-ghost" style={{ fontSize: 12 }} onClick={togglePin}>
              {entry.pinned ? 'Unpin' : 'Pin'}
            </button>
            <button className="btn-ghost" style={{ fontSize: 12 }} onClick={onClose}>✕ Close</button>
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Meta grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <Field label="Owner" value={entry.owner} />
            <Field label="Responsible" value={entry.responsible.join(', ') || '—'} />
            <Field label="Category" value={entry.category || '—'} />
            <Field label="Due Date" value={entry.due_date ?? '—'} highlight={entry.status === 'overdue'} />
            <Field label="Start Date" value={entry.start_date ?? '—'} />
            <Field label="Input Date" value={entry.input_date ?? '—'} />
          </div>

          {entry.description && (
            <div><label>Description</label><div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{entry.description}</div></div>
          )}
          {entry.remarks && (
            <div><label>Remarks / Status Update</label><div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{entry.remarks}</div></div>
          )}

          {/* Notes */}
          <div>
            <label>Notes ({entry.notes.length})</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
              {entry.notes.slice().reverse().map((n, i) => (
                <div key={i} style={{ background: '#f9fafb', border: '1px solid var(--border)', borderRadius: 4, padding: '8px 12px' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{n.by} · {n.at}</div>
                  <div style={{ fontSize: 13 }}>{n.text}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Subtasks */}
          {entry.subtasks.length > 0 && (
            <div>
              <label>Subtasks ({entry.subtasks.length})</label>
              <div style={{ marginTop: 6 }}>
                {entry.subtasks.map(s => (
                  <div key={s.id} style={{ display: 'flex', gap: 8, padding: '6px 0', borderBottom: '1px solid #f0f0f0', alignItems: 'center' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)', minWidth: 70 }}>{s.id}</span>
                    <span style={{ flex: 1, fontSize: 13 }}>{s.subject}</span>
                    <StatusBadge status={s.status} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="Add a note…"
              rows={2}
              style={{ flex: 1, resize: 'none' }}
            />
            <button className="btn-primary" onClick={addNote} disabled={saving || !note.trim()}>Add Note</button>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select value={newStatus} onChange={e => setNewStatus(e.target.value as OPLStatus)} style={{ width: 180 }}>
              <option value="">Change status…</option>
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button className="btn-ghost" onClick={changeStatus} disabled={!newStatus || saving}>Apply</button>
          </div>
        </div>
      </div>
    </Overlay>
  )
}

function Overlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100,
      display: 'flex', justifyContent: 'flex-end',
    }} onClick={onClose}>
      <div style={{
        width: 640, maxWidth: '95vw', height: '100%', background: 'var(--surface)',
        boxShadow: '-4px 0 24px rgba(0,0,0,0.15)', overflow: 'hidden',
      }} onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <label>{label}</label>
      <div style={{ fontSize: 13, fontWeight: 500, color: highlight ? 'var(--danger)' : undefined }}>{value}</div>
    </div>
  )
}
