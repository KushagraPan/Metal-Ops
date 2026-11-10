import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { api } from '../api/client'
import type { Report, ReportResult } from '../api/client'

interface HeatReportsProps {
  heatId: number
  reports: Report[]
  onChanged?: (() => void) | undefined
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

function resultLabel(result: ReportResult): string {
  if (result === 'PASS') {
    return 'Pass'
  }
  if (result === 'FAIL') {
    return 'Fail'
  }
  return 'Pending'
}

function dateTimeLabel(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('en-IN')
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

export default function HeatReports({
  heatId,
  reports,
  onChanged,
}: HeatReportsProps) {
  const [rows, setRows] = useState<Report[]>(reports)
  const [sampleNo, setSampleNo] = useState('')
  const [result, setResult] = useState<ReportResult>('PENDING')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editResult, setEditResult] = useState<ReportResult>('PENDING')
  const [editNotes, setEditNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setRows(reports)
  }, [reports])

  const editing = rows.find((row) => row.id === editingId) ?? null

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (file === null) {
      setError('Choose a PDF file.')
      return
    }
    const cleanSampleNo = sampleNo.trim()
    if (cleanSampleNo === '') {
      setError('Sample number is required.')
      return
    }
    setUploading(true)
    try {
      const created = await api.reports.upload(heatId, {
        file,
        sample_no: cleanSampleNo,
        result,
        notes: notes.trim() === '' ? null : notes.trim(),
      })
      setRows((current) => [...current, created])
      setSampleNo('')
      setNotes('')
      setResult('PENDING')
      setFile(null)
      if (fileInput.current !== null) {
        fileInput.current.value = ''
      }
      onChanged?.()
    } catch (uploadError) {
      setError(messageOf(uploadError))
    } finally {
      setUploading(false)
    }
  }

  function startEdit(report: Report): void {
    setEditingId(report.id)
    setEditResult(report.result)
    setEditNotes(report.notes ?? '')
    setError(null)
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (editing === null) {
      return
    }
    setSaving(true)
    setError(null)
    try {
      const updated = await api.reports.update(editing.id, {
        result: editResult,
        notes: editNotes.trim() === '' ? null : editNotes.trim(),
      })
      setRows((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      )
      setEditingId(null)
      onChanged?.()
    } catch (updateError) {
      setError(messageOf(updateError))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(report: Report): Promise<void> {
    if (!window.confirm(`Delete report ${report.sample_no}?`)) {
      return
    }
    setError(null)
    try {
      await api.reports.remove(report.id)
      setRows((current) => current.filter((row) => row.id !== report.id))
      if (editingId === report.id) {
        setEditingId(null)
      }
      onChanged?.()
    } catch (deleteError) {
      setError(messageOf(deleteError))
    }
  }

  return (
    <section className="report-section">
      <h3>Spectro reports</h3>
      {error !== null ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="muted">No reports uploaded.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sample</th>
                <th>Uploaded</th>
                <th>Result</th>
                <th>Notes</th>
                <th>File</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((report) => (
                <tr key={report.id}>
                  <td>
                    <strong>{report.sample_no}</strong>
                  </td>
                  <td>{dateTimeLabel(report.uploaded_at)}</td>
                  <td>{resultLabel(report.result)}</td>
                  <td>{report.notes ?? '—'}</td>
                  <td>
                    {report.original_filename}{' '}
                    <span className="muted">
                      ({sizeLabel(report.size_bytes)})
                    </span>
                  </td>
                  <td className="actions">
                    <a
                      href={api.reports.downloadUrl(report.id)}
                      aria-label={`Download report ${report.sample_no}`}
                    >
                      Download
                    </a>
                    <button
                      type="button"
                      aria-label={`Edit report ${report.sample_no}`}
                      onClick={() => startEdit(report)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="danger"
                      aria-label={`Delete report ${report.sample_no}`}
                      onClick={() => {
                        void handleDelete(report)
                      }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== null ? (
        <form className="report-edit" onSubmit={handleEdit}>
          <h4>Edit report {editing.sample_no}</h4>
          <div className="form-grid">
            <label className="field">
              <span>Edit result</span>
              <select
                value={editResult}
                onChange={(event) =>
                  setEditResult(event.target.value as ReportResult)
                }
              >
                <option value="PENDING">Pending</option>
                <option value="PASS">Pass</option>
                <option value="FAIL">Fail</option>
              </select>
            </label>
            <label className="field">
              <span>Edit notes</span>
              <textarea
                rows={2}
                value={editNotes}
                onChange={(event) => setEditNotes(event.target.value)}
              />
            </label>
          </div>
          <div className="actions">
            <button type="submit" className="primary" disabled={saving}>
              Save changes
            </button>
            <button type="button" onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      <form className="report-upload" onSubmit={handleUpload}>
        <h4>Upload a report</h4>
        <div className="form-grid">
          <label className="field">
            <span>Sample number</span>
            <input
              type="text"
              maxLength={50}
              value={sampleNo}
              onChange={(event) => setSampleNo(event.target.value)}
            />
          </label>
          <label className="field">
            <span>PDF file</span>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) =>
                setFile(event.target.files?.[0] ?? null)
              }
            />
          </label>
          <label className="field">
            <span>Result</span>
            <select
              value={result}
              onChange={(event) =>
                setResult(event.target.value as ReportResult)
              }
            >
              <option value="PENDING">Pending</option>
              <option value="PASS">Pass</option>
              <option value="FAIL">Fail</option>
            </select>
          </label>
          <label className="field">
            <span>Notes</span>
            <textarea
              rows={2}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
        </div>
        <div className="actions">
          <button type="submit" className="primary" disabled={uploading}>
            {uploading ? 'Uploading...' : 'Upload report'}
          </button>
        </div>
      </form>
    </section>
  )
}
