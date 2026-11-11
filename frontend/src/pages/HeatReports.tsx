import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { FileText, Upload } from 'lucide-react'

import { api } from '../api/client'
import type { Report, ReportResult } from '../api/client'
import { Select } from '../components/ui/select'
import { Badge } from '../components/ui/badge'

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
    <div className="rounded-xl border border-border bg-card p-5 space-y-5">
      {/* 1. Header with title and small count */}
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div>
          <h3 className="text-base font-semibold text-foreground">
            Spectro reports
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Laboratory spectro testing certificates and alloy composition analysis.
          </p>
        </div>
        <span className="text-xs font-medium text-muted-foreground">
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

      {/* Reports Table or Clean Empty State inside Card Body */}
      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center bg-muted/10">
          <FileText className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
          <p className="text-sm font-medium text-foreground">
            No reports uploaded.
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Upload the first spectro report PDF using the form below.
          </p>
        </div>
      ) : (
        <div className="table-wrap rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground bg-muted/20">
                <th className="py-2.5 px-3">Sample</th>
                <th className="py-2.5 px-3">Uploaded</th>
                <th className="py-2.5 px-3">Result</th>
                <th className="py-2.5 px-3">Notes</th>
                <th className="py-2.5 px-3">File</th>
                <th className="py-2.5 px-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {rows.map((report) => (
                <tr key={report.id} className="hover:bg-muted/40 transition-colors">
                  <td className="py-2.5 px-3">
                    <strong className="text-foreground">{report.sample_no}</strong>
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">
                    {dateTimeLabel(report.uploaded_at)}
                  </td>
                  <td className="py-2.5 px-3">
                    <Badge
                      variant={
                        report.result === 'PASS'
                          ? 'emerald'
                          : report.result === 'FAIL'
                            ? 'rose'
                            : 'amber'
                      }
                      className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5"
                    >
                      {resultLabel(report.result)}
                    </Badge>
                  </td>
                  <td className="py-2.5 px-3 text-foreground">{report.notes ?? '—'}</td>
                  <td className="py-2.5 px-3 text-muted-foreground whitespace-nowrap">
                    {report.original_filename}{' '}
                    <span className="text-xs">
                      ({sizeLabel(report.size_bytes)})
                    </span>
                  </td>
                  <td className="py-2.5 px-3 actions whitespace-nowrap">
                    <button
                      type="button"
                      aria-label={`Download report ${report.sample_no}`}
                      className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => {
                        void handleDownload(report)
                      }}
                    >
                      Download
                    </button>
                    <button
                      type="button"
                      aria-label={`Edit report ${report.sample_no}`}
                      className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => startEdit(report)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete report ${report.sample_no}`}
                      className="inline-flex h-8 items-center justify-center rounded-md border border-rose-200 dark:border-rose-900/40 bg-card px-2.5 text-xs font-medium text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
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
          className="rounded-lg border border-border bg-muted/20 p-4 space-y-3"
          onSubmit={handleEdit}
        >
          <div className="border-b border-border pb-2">
            <h4 className="text-sm font-semibold text-foreground">
              Edit report {editing.sample_no}
            </h4>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="edit-result" className="text-xs font-semibold text-muted-foreground">
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
            <div className="flex flex-col gap-1.5">
              <label htmlFor="edit-notes" className="text-xs font-semibold text-muted-foreground">
                Edit notes
              </label>
              <input
                id="edit-notes"
                type="text"
                aria-label="Edit notes"
                value={editNotes}
                onChange={(event) => setEditNotes(event.target.value)}
                className="h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={() => setEditingId(null)}
              className="inline-flex h-9 items-center justify-center rounded-input border border-border bg-card px-3.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex h-9 items-center justify-center rounded-input bg-primary px-3.5 text-xs font-semibold text-primary-foreground shadow-sm transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Save changes
            </button>
          </div>
        </form>
      )}

      {/* Upload Form Container within the Card */}
      <div className="border-t border-border pt-4 space-y-4">
        <div>
          <h4 className="text-sm font-semibold text-foreground">
            Upload a report
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            Attach spectrometer test certificate PDF for sample tracking and chemical verification.
          </p>
        </div>

        <form onSubmit={handleUpload} className="space-y-4">
          {/* 2 & 3. 4-column responsive grid with h-10 controls and labels directly above */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            {/* Field 1: Sample number */}
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="upload-sample-no"
                className="text-xs font-semibold text-muted-foreground"
              >
                Sample number
              </label>
              <input
                id="upload-sample-no"
                type="text"
                maxLength={50}
                value={sampleNo}
                placeholder="e.g. S-2026-001"
                aria-label="Sample number"
                onChange={(event) => setSampleNo(event.target.value)}
                className="h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2"
              />
            </div>

            {/* Field 2: Custom PDF File Upload (4. Accessible label-styled trigger) */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-muted-foreground">
                PDF file
              </span>
              <label
                htmlFor="upload-pdf-file"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    fileInput.current?.click()
                  }
                }}
                className="flex h-10 w-full cursor-pointer items-center justify-between rounded-input border border-dashed border-border bg-card px-3 text-sm text-foreground transition-colors hover:border-primary hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <span className="truncate pr-2 text-muted-foreground font-normal">
                  {file ? file.name : 'Choose PDF...'}
                </span>
                <Upload className="h-4 w-4 shrink-0 text-muted-foreground" />
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
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="upload-result"
                className="text-xs font-semibold text-muted-foreground"
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
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="upload-notes"
                className="text-xs font-semibold text-muted-foreground"
              >
                Notes
              </label>
              <input
                id="upload-notes"
                type="text"
                value={notes}
                placeholder="Optional notes"
                aria-label="Notes"
                onChange={(event) => setNotes(event.target.value)}
                className="h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2"
              />
            </div>
          </div>

          {/* 5. Right-aligned primary amber button in form footer */}
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={uploading}
              className="inline-flex h-10 items-center justify-center rounded-input bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-sm transition hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {uploading ? 'Uploading...' : 'Upload report'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
