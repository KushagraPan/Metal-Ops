import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { FileText, Upload } from 'lucide-react'

import { api } from '../api/client'
import type { Report, ReportResult } from '../api/client'
import { Select } from '../components/ui/select'

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

  async function handleDownload(report: Report): Promise<void> {
    setError(null)
    try {
      const blob = await api.reports.download(report.id)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = report.original_filename || `report-${report.sample_no}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (downloadError) {
      setError(messageOf(downloadError))
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
    <div className="space-y-6">
      {/* 4. Structured Header for Spectro Reports */}
      <div className="border-b border-slate-200 pb-3 dark:border-slate-800 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Spectro reports
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Laboratory spectro testing certificates and alloy composition analysis.
          </p>
        </div>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {rows.length} {rows.length === 1 ? 'report' : 'reports'}
        </span>
      </div>

      {error !== null && (
        <div
          role="alert"
          className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
        >
          {error}
        </div>
      )}

      {/* Reports Table or Clean Empty State */}
      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 p-8 text-center dark:border-slate-800">
          <FileText className="mx-auto h-8 w-8 text-slate-400 dark:text-slate-600 mb-2" />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
            No reports uploaded.
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Upload the first spectro report PDF using the form below.
          </p>
        </div>
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
                  <td>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                        report.result === 'PASS'
                          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300'
                          : report.result === 'FAIL'
                            ? 'bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300'
                            : 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                      }`}
                    >
                      {resultLabel(report.result)}
                    </span>
                  </td>
                  <td>{report.notes ?? '—'}</td>
                  <td>
                    {report.original_filename}{' '}
                    <span className="muted text-xs">
                      ({sizeLabel(report.size_bytes)})
                    </span>
                  </td>
                  <td className="actions">
                    <button
                      type="button"
                      aria-label={`Download report ${report.sample_no}`}
                      onClick={() => {
                        void handleDownload(report)
                      }}
                    >
                      Download
                    </button>
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

      {/* Edit Form */}
      {editing !== null && (
        <form
          className="app-card space-y-3"
          onSubmit={handleEdit}
        >
          <div className="border-b border-slate-200 pb-2 dark:border-slate-800">
            <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Edit report {editing.sample_no}
            </h4>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
            <div className="flex flex-col">
              <label htmlFor="edit-result" className="app-label">
                Edit result
              </label>
              <Select
                id="edit-result"
                label="Edit result"
                value={editResult}
                options={[
                  { value: 'PENDING', label: 'Pending' },
                  { value: 'PASS', label: 'Pass' },
                  { value: 'FAIL', label: 'Fail' },
                ]}
                onChange={(value) => setEditResult(value as ReportResult)}
              />
            </div>
            <div className="flex flex-col">
              <label htmlFor="edit-notes" className="app-label">
                Edit notes
              </label>
              <input
                id="edit-notes"
                type="text"
                value={editNotes}
                onChange={(event) => setEditNotes(event.target.value)}
                className="app-input"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={() => setEditingId(null)}
              className="inline-flex h-10 items-center justify-center rounded-input border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="app-btn-primary"
            >
              Save changes
            </button>
          </div>
        </form>
      )}

      {/* Upload Form Container */}
      <div className="app-card space-y-4">
        {/* 4. Structured Header for Upload Form */}
        <div className="border-b border-slate-200/80 pb-2 dark:border-slate-800">
          <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Upload a report
          </h4>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Attach spectrometer test certificate PDF for sample tracking and chemical verification.
          </p>
        </div>

        <form onSubmit={handleUpload} className="space-y-4">
          {/* 1. Responsive Grid & 2. Uniform h-10 Controls */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            {/* Field 1: Sample number */}
            <div className="flex flex-col">
              <label
                htmlFor="upload-sample-no"
                className="app-label"
              >
                Sample number
              </label>
              <input
                id="upload-sample-no"
                type="text"
                maxLength={50}
                value={sampleNo}
                placeholder="e.g. S-2026-001"
                onChange={(event) => setSampleNo(event.target.value)}
                className="app-input"
              />
            </div>

            {/* Field 2: Custom PDF File Upload (3. Hidden native input with styled trigger) */}
            <div className="flex flex-col">
              <span className="app-label">
                PDF file
              </span>
              <label
                htmlFor="upload-pdf-file"
                className="app-input flex cursor-pointer items-center justify-between border-dashed hover:border-brand-500"
              >
                <span className="truncate pr-2">
                  {file ? file.name : 'Choose PDF...'}
                </span>
                <Upload className="h-4 w-4 flex-shrink-0 text-slate-400" />
                <input
                  id="upload-pdf-file"
                  ref={fileInput}
                  type="file"
                  aria-label="PDF file"
                  accept="application/pdf,.pdf"
                  onChange={(event) =>
                    setFile(event.target.files?.[0] ?? null)
                  }
                  className="sr-only"
                />
              </label>
            </div>

            {/* Field 3: Result */}
            <div className="flex flex-col">
              <label
                htmlFor="upload-result"
                className="app-label"
              >
                Result
              </label>
              <Select
                id="upload-result"
                label="Result"
                value={result}
                options={[
                  { value: 'PENDING', label: 'Pending' },
                  { value: 'PASS', label: 'Pass' },
                  { value: 'FAIL', label: 'Fail' },
                ]}
                onChange={(value) => setResult(value as ReportResult)}
              />
            </div>

            {/* Field 4: Notes (Single-line input, h-10) */}
            <div className="flex flex-col">
              <label
                htmlFor="upload-notes"
                className="app-label"
              >
                Notes
              </label>
              <input
                id="upload-notes"
                type="text"
                value={notes}
                placeholder="Optional notes"
                onChange={(event) => setNotes(event.target.value)}
                className="app-input"
              />
            </div>
          </div>

          <div className="flex justify-end pt-1">
            <button
              type="submit"
              disabled={uploading}
              className="app-btn-primary"
            >
              {uploading ? 'Uploading...' : 'Upload report'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
