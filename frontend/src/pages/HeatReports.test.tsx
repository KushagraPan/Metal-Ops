// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { Report } from '../api/client'
import HeatReports from './HeatReports'

vi.mock('../api/client', () => ({
  api: {
    reports: {
      upload: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      download: vi.fn(),
      downloadUrl: vi.fn(),
    },
  },
}))

const report: Report = {
  id: 7,
  heat_id: 4,
  sample_no: 'S-1',
  original_filename: 'sample.pdf',
  size_bytes: 1234,
  uploaded_at: '2026-10-15T09:30:00+00:00',
  grade_tested: 'ADC12',
  result: 'PASS',
  notes: 'Looks good',
  elements: null,
}

beforeEach(() => {
  vi.mocked(api.reports.downloadUrl).mockImplementation(
    (id: number) => `/api/reports/${id}/download`,
  )
})

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('HeatReports', () => {
  it('lists reports with result, notes and a download button', () => {
    render(<HeatReports heatId={4} reports={[report]} />)

    expect(screen.getByText('S-1')).toBeDefined()
    expect(within(screen.getByRole('table')).getByText('Pass')).toBeDefined()
    expect(screen.getByText('Looks good')).toBeDefined()
    const downloadBtn = screen.getByRole('button', { name: 'Download report S-1' })
    expect(downloadBtn).toBeDefined()
  })

  it('downloads a report through the API client', async () => {
    const dummyBlob = new Blob(['dummy pdf'], { type: 'application/pdf' })
    vi.mocked(api.reports.download).mockResolvedValue(dummyBlob)
    const createObjectURLSpy = vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:http://localhost/dummy')
    const revokeObjectURLSpy = vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {})

    render(<HeatReports heatId={4} reports={[report]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Download report S-1' }))

    await waitFor(() => {
      expect(api.reports.download).toHaveBeenCalledWith(7)
    })
    expect(createObjectURLSpy).toHaveBeenCalledWith(dummyBlob)
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:http://localhost/dummy')
  })

  it('uploads a report and adds it to the list', async () => {
    const created: Report = { ...report, id: 8, sample_no: 'S-2' }
    vi.mocked(api.reports.upload).mockResolvedValue(created)

    render(<HeatReports heatId={4} reports={[]} />)

    fireEvent.change(screen.getByLabelText('Sample number'), {
      target: { value: 'S-2' },
    })
    fireEvent.change(screen.getByLabelText('PDF file'), {
      target: {
        files: [
          new File(['%PDF-1.4'], 'report.pdf', {
            type: 'application/pdf',
          }),
        ],
      },
    })
    fireEvent.change(screen.getByLabelText('Notes'), {
      target: { value: 'New note' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload report' }))

    expect(await screen.findByText('S-2')).toBeDefined()
    expect(api.reports.upload).toHaveBeenCalledWith(
      4,
      expect.objectContaining({
        sample_no: 'S-2',
        result: 'PENDING',
        notes: 'New note',
      }),
    )
  })

  it('edits the result and notes after upload', async () => {
    const updated: Report = { ...report, result: 'FAIL', notes: 'Retest' }
    vi.mocked(api.reports.update).mockResolvedValue(updated)

    render(<HeatReports heatId={4} reports={[report]} />)

    fireEvent.click(screen.getByLabelText('Edit report S-1'))
    fireEvent.change(screen.getByLabelText('Edit result'), {
      target: { value: 'FAIL' },
    })
    fireEvent.change(screen.getByLabelText('Edit notes'), {
      target: { value: 'Retest' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(
      await within(screen.getByRole('table')).findByText('Fail'),
    ).toBeDefined()
    expect(screen.getByText('Retest')).toBeDefined()
    expect(api.reports.update).toHaveBeenCalledWith(7, {
      result: 'FAIL',
      notes: 'Retest',
    })
  })

  it('deletes a report', async () => {
    vi.mocked(api.reports.remove).mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<HeatReports heatId={4} reports={[report]} />)

    fireEvent.click(screen.getByLabelText('Delete report S-1'))

    await waitFor(() => {
      expect(screen.queryByText('S-1')).toBeNull()
    })
    expect(api.reports.remove).toHaveBeenCalledWith(7)
  })

  it('shows a clear upload error', async () => {
    vi.mocked(api.reports.upload).mockRejectedValue(
      new Error('file must be a PDF'),
    )

    render(<HeatReports heatId={4} reports={[]} />)

    fireEvent.change(screen.getByLabelText('Sample number'), {
      target: { value: 'S-2' },
    })
    fireEvent.change(screen.getByLabelText('PDF file'), {
      target: {
        files: [
          new File(['not a pdf'], 'report.pdf', {
            type: 'application/pdf',
          }),
        ],
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Upload report' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('file must be a PDF')
  })
})
