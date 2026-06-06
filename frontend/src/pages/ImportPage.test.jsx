import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import ImportPage from './ImportPage'

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')

  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

vi.mock('../components/AccountSelector', () => ({
  default: ({ value = 'all', onChange, label = 'Target Account' }) => (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">All Accounts</option>
        <option value="7">Everyday Chequing</option>
        <option value="9">Savings</option>
      </select>
    </label>
  ),
}))

const previewRows = [
  {
    date: '2026-05-01',
    description: 'Coffee shop',
    amount: 6.5,
    type: 'expense',
    category: 'cafe',
    source_line: '2026-05-01 Coffee shop 6.50',
    confidence: 0.96,
    category_confidence: 0.94,
    category_review_required: false,
    is_duplicate: false,
  },
  {
    date: '2026-05-02',
    description: 'Already paid',
    amount: 25,
    type: 'expense',
    category: 'transport',
    source_line: '2026-05-02 Already paid 25.00',
    confidence: 0.98,
    category_confidence: 0.91,
    category_review_required: false,
    is_duplicate: true,
    duplicate_reason: 'Already written transaction matched.',
  },
  {
    date: '2026-05-03',
    description: 'Mystery merchant',
    amount: 18.75,
    type: 'expense',
    category: 'other',
    source_line: '2026-05-03 Mystery merchant 18.75',
    confidence: 0.93,
    category_confidence: 0.41,
    category_review_required: true,
    category_review_reason: 'Low confidence category suggestion.',
    is_duplicate: false,
  },
]

function mockImportRequests() {
  api.post.mockImplementation((path) => {
    if (path === '/transactions/import/file') {
      return Promise.resolve({
        data: {
          status: 'table_review',
          detected_type: 'pdf_statement',
          preview_rows: previewRows,
          notes: ['3 rows detected for review.'],
        },
      })
    }
    if (path === '/transactions/import/confirm-preview') {
      return Promise.resolve({
        data: {
          message: 'Imported 2 rows.',
          imported: 2,
          duplicates_skipped: 0,
          invalid_rows_skipped: 0,
        },
      })
    }
    return Promise.reject(new Error(`Unexpected POST ${path}`))
  })
}

function renderImportPage() {
  return render(
    <MemoryRouter initialEntries={['/import']}>
      <LanguageProvider>
        <ImportPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

function getFileInput(container) {
  return container.querySelector('input[type="file"]')
}

function uploadStatement(container) {
  const file = new File(['fake statement bytes'], 'statement.pdf', {
    type: 'application/pdf',
  })
  fireEvent.change(getFileInput(container), {
    target: { files: [file] },
  })
}

describe('ImportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockImportRequests()
  })

  it('blocks file upload until a specific account is selected', async () => {
    const { container } = renderImportPage()

    uploadStatement(container)

    expect(await screen.findByText('Please select a specific account before importing a file.')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('reviews statement preview rows, removes duplicates, approves a category, and confirms import', async () => {
    const user = userEvent.setup()
    const { container } = renderImportPage()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Target Account' }), '7')
    uploadStatement(container)

    expect(await screen.findByText('Review Statement Rows')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Coffee shop')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Already paid')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Mystery merchant')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import Ready Rows (1)' })).toBeEnabled()

    const uploadCall = api.post.mock.calls.find(([path]) => path === '/transactions/import/file')
    expect(uploadCall[1]).toBeInstanceOf(FormData)
    expect(uploadCall[1].get('account_id')).toBe('7')
    expect(uploadCall[1].get('file').name).toBe('statement.pdf')

    await user.click(screen.getByRole('button', { name: 'Remove Already Written' }))
    expect(screen.queryByDisplayValue('Already paid')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Approve Category' }))
    await user.click(screen.getByRole('button', { name: 'Import Ready Rows (2)' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/transactions/import/confirm-preview', {
        account_id: 7,
        rows: [
          expect.objectContaining({ description: 'Coffee shop' }),
          expect.objectContaining({ description: 'Mystery merchant', category: 'other' }),
        ],
      })
    })
    expect(await screen.findByText('Import completed')).toBeInTheDocument()
    expect(screen.getByText('Imported 2 rows.')).toBeInTheDocument()
    expect(screen.getByText('Imported')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows skipped source row diagnostics during statement review', async () => {
    api.post.mockImplementation((path) => {
      if (path === '/transactions/import/file') {
        return Promise.resolve({
          data: {
            status: 'table_review',
            detected_type: 'csv_statement',
            preview_rows: [previewRows[0]],
            import_summary: {
              imported: 0,
              duplicates_skipped: 0,
              invalid_rows_skipped: 1,
              invalid_row_details: ['CSV row 356: amount is missing or not a number.'],
            },
            notes: ['Matched rows are already in your app. Missing rows can be imported after review.'],
          },
        })
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`))
    })

    const user = userEvent.setup()
    const { container } = renderImportPage()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Target Account' }), '7')
    uploadStatement(container)

    expect(await screen.findByText('1 source row skipped')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Rows with missing dates, descriptions, or amounts are not imported. Review the row numbers in your source file if the count looks wrong.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('CSV row 356: amount is missing or not a number.')).toBeInTheDocument()
  })

  it('logs sanitized upload diagnostics when import fails', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    api.post.mockImplementation((path) => {
      if (path === '/transactions/import/file') {
        return Promise.reject({
          response: {
            status: 500,
            data: {
              detail: 'Smart import failed.',
              request_id: 'request-123',
              stage: 'csv_statement_parse',
            },
            headers: {
              'x-request-id': 'request-123',
            },
          },
        })
      }
      return Promise.reject(new Error(`Unexpected POST ${path}`))
    })

    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    const { container } = renderImportPage()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Target Account' }), '7')
    const file = new File(['fake csv bytes'], 'personal-statement.csv', {
      type: 'text/csv',
    })
    fireEvent.change(getFileInput(container), {
      target: { files: [file] },
    })

    expect(await screen.findByText(/Smart import failed/)).toBeInTheDocument()
    expect(screen.getByText('Safe diagnostics')).toBeInTheDocument()
    expect(screen.getByText('500')).toBeInTheDocument()
    expect(screen.getByText('request-123')).toBeInTheDocument()
    expect(screen.getByText('csv_statement_parse')).toBeInTheDocument()
    expect(
      screen.getByText((content) => content.includes('CSV') && content.includes('text/csv')),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Copy diagnostics' }))

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledTimes(1)
    })
    expect(writeText.mock.calls[0][0]).toContain('Request ID: request-123')
    expect(writeText.mock.calls[0][0]).toContain('Import stage: csv_statement_parse')
    expect(writeText.mock.calls[0][0]).not.toContain('personal-statement.csv')
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()

    expect(consoleSpy).toHaveBeenCalledWith(
      'Import upload failed',
      expect.objectContaining({
        uploadPath: '/transactions/import/file',
        status: 500,
        requestId: 'request-123',
        stage: 'csv_statement_parse',
        fileCount: 1,
        files: [
          expect.objectContaining({
            extension: 'csv',
            type: 'text/csv',
            size: expect.any(Number),
          }),
        ],
      }),
    )
    expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain('personal-statement.csv')
    consoleSpy.mockRestore()
  })
})
