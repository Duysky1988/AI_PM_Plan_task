import { useState } from 'react'
import { api } from '../../api/client'
import type { OPLEntryType, Priority } from '../../types'
import './OPLForm.css'

interface Props { onClose: () => void; parentId?: string }

export default function OPLForm({ onClose, parentId }: Props) {
  const [form, setForm] = useState({
    entry_type: 'Task' as OPLEntryType,
    subject: '', description: '',
    owner: '', priority: 'Medium' as Priority, due_date: '',
    category: '', register: '', tags: '',
    parent_id: parentId ?? '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.subject.trim()) { setError('Subject is required'); return }
    if (!form.owner.trim()) { setError('Owner is required'); return }
    setSaving(true)
    try {
      await api.opl.create({
        ...form,
        tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
        parent_id: form.parent_id || null,
      })
      onClose()
    } catch (err) {
      setError(String(err))
      setSaving(false)
    }
  }

  return (
    <div className="opl-form-overlay" onClick={onClose}>
      <div className="opl-form-dialog" onClick={e => e.stopPropagation()}>
        <h2 className="opl-form-title">New OPL Entry</h2>
        <form onSubmit={submit} className="opl-form-body">

          <div className="form-row-2col">
            <div className="form-field">
              <label htmlFor="opl-entry-type">Type</label>
              <select
                id="opl-entry-type"
                title="Entry type"
                value={form.entry_type}
                onChange={e => set('entry_type', e.target.value)}
              >
                {(['Task', 'Information', 'Decision', 'Subtask'] as OPLEntryType[]).map(t =>
                  <option key={t} value={t}>{t}</option>
                )}
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="opl-priority">Priority</label>
              <select
                id="opl-priority"
                title="Priority level"
                value={form.priority}
                onChange={e => set('priority', e.target.value)}
              >
                {(['High', 'Medium', 'Low'] as Priority[]).map(p =>
                  <option key={p} value={p}>{p}</option>
                )}
              </select>
            </div>
          </div>

          <div className="form-field">
            <label htmlFor="opl-subject">Subject *</label>
            <input
              id="opl-subject"
              value={form.subject}
              onChange={e => set('subject', e.target.value)}
              placeholder="Short description of the task"
            />
          </div>

          <div className="form-field">
            <label htmlFor="opl-description">Description</label>
            <textarea
              id="opl-description"
              value={form.description}
              onChange={e => set('description', e.target.value)}
              placeholder="Detailed description (optional)"
              rows={3}
              className="opl-textarea-resize"
            />
          </div>

          <div className="form-row-2col">
            <div className="form-field">
              <label htmlFor="opl-owner">Owner *</label>
              <input
                id="opl-owner"
                value={form.owner}
                onChange={e => set('owner', e.target.value)}
                placeholder="Display name or NT login"
              />
            </div>
            <div className="form-field">
              <label htmlFor="opl-due-date">Due Date</label>
              <input
                id="opl-due-date"
                type="date"
                title="Due date"
                value={form.due_date}
                onChange={e => set('due_date', e.target.value)}
              />
            </div>
          </div>

          <div className="form-row-2col">
            <div className="form-field">
              <label htmlFor="opl-category">Category</label>
              <input
                id="opl-category"
                value={form.category}
                onChange={e => set('category', e.target.value)}
                placeholder="e.g. SW, HW, SYS"
              />
            </div>
            <div className="form-field">
              <label htmlFor="opl-register">Register (Rele)</label>
              <input
                id="opl-register"
                value={form.register}
                onChange={e => set('register', e.target.value)}
                placeholder="e.g. PjM, SW"
              />
            </div>
          </div>

          <div className="form-field">
            <label htmlFor="opl-tags">Tags (comma-separated)</label>
            <input
              id="opl-tags"
              value={form.tags}
              onChange={e => set('tags', e.target.value)}
              placeholder="tag1, tag2"
            />
          </div>

          {parentId && (
            <div className="form-field">
              <label htmlFor="opl-parent-id">Parent ID</label>
              <input
                id="opl-parent-id"
                value={form.parent_id}
                readOnly
                title="Parent entry ID"
                className="opl-input-readonly"
              />
            </div>
          )}

          {error && <p className="opl-form-error">{error}</p>}

          <div className="opl-form-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : 'Create Entry'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
