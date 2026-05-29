import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import AssistantPage from './AssistantPage'

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
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

vi.mock('../components/AccountSelector', () => ({
  default: ({ value = 'all', onChange, label = 'Assistant scope' }) => (
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

const assistantStatus = {
  active_provider: 'local',
  message: 'Local assistant ready.',
  providers: [
    { id: 'rule_based', label: 'Rule-based fallback', active: false },
    { id: 'local', label: 'Local LLM', active: true },
  ],
  daily_limit: 10,
  daily_remaining: 7,
  daily_char_limit: 5000,
  daily_chars_remaining: 4300,
}

const historyPayload = {
  messages: [
    { role: 'user', content: 'What changed this week?' },
    {
      role: 'assistant',
      content: 'Groceries rose last week.',
      scope_label: 'All accounts',
    },
  ],
}

const assistantAnswer = {
  answer: 'Groceries rose by $120 compared with your usual pace.',
  scope_label: 'Savings account',
  supporting_points: ['Groceries were the largest category this month.'],
  suggested_followups: ['Which transactions caused that?'],
  suggested_actions: [
    {
      label: 'Open groceries ledger',
      page: 'transactions',
      category: 'groceries',
      month: '2026-05',
    },
  ],
}

function mockAssistantRequests() {
  api.get.mockImplementation((path) => {
    if (path === '/assistant/status') {
      return Promise.resolve({ data: assistantStatus })
    }
    if (path === '/assistant/history') {
      return Promise.resolve({ data: historyPayload })
    }
    return Promise.reject(new Error(`Unexpected GET ${path}`))
  })
  api.post.mockResolvedValue({ data: assistantAnswer })
  api.delete.mockResolvedValue({ data: {} })
}

function renderAssistantPage() {
  return render(
    <MemoryRouter initialEntries={['/assistant']}>
      <LanguageProvider>
        <AssistantPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

async function waitForAssistantHistory() {
  expect(await screen.findByText('Groceries rose last week.')).toBeInTheDocument()
}

describe('AssistantPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockAssistantRequests()
  })

  it('loads provider status and saved assistant history', async () => {
    renderAssistantPage()

    await waitForAssistantHistory()

    expect(screen.getByText('Local LLM')).toBeInTheDocument()
    expect(screen.getByText('Local assistant ready.')).toBeInTheDocument()
    expect(screen.getByText('7 of 10 AI replies left in the last 24 hours.')).toBeInTheDocument()
    expect(screen.getByText('4300 of 5000 AI characters left.')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/assistant/status')
    expect(api.get).toHaveBeenCalledWith('/assistant/history', {
      params: { account_id: undefined },
    })
  })

  it('sends a scoped question and renders answer details, followups, and actions', async () => {
    const user = userEvent.setup()
    renderAssistantPage()

    await waitForAssistantHistory()

    await user.selectOptions(screen.getByLabelText('Personality mode'), 'strict')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Assistant scope' }), '9')
    await user.type(
      screen.getByPlaceholderText('Ask anything about your money, habits, budget, or next move...'),
      'How did groceries change?',
    )
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/assistant/response', {
        question: 'How did groceries change?',
        history: expect.arrayContaining([
          expect.objectContaining({
            role: 'user',
            content: 'How did groceries change?',
          }),
        ]),
        mode: 'strict',
        account_id: 9,
      })
    })
    expect(await screen.findByText('Groceries rose by $120 compared with your usual pace.')).toBeInTheDocument()
    expect(screen.getByText('Savings account')).toBeInTheDocument()
    expect(screen.getByText('Groceries were the largest category this month.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Which transactions caused that?' }))
    expect(screen.getByPlaceholderText('Ask anything about your money, habits, budget, or next move...')).toHaveValue(
      'Which transactions caused that?',
    )

    await user.click(screen.getByRole('button', { name: 'Open groceries ledger' }))
    expect(mockNavigate).toHaveBeenCalledWith('/transactions?category=groceries&month=2026-05')
  })

  it('clears saved assistant history for the current scope', async () => {
    const user = userEvent.setup()
    renderAssistantPage()

    await waitForAssistantHistory()
    await user.click(screen.getByRole('button', { name: 'Clear conversation' }))

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/assistant/history', {
        params: { account_id: undefined },
      })
    })
    expect(screen.queryByText('Groceries rose last week.')).not.toBeInTheDocument()
    expect(screen.getByText(/Hi - I'm your financial assistant/)).toBeInTheDocument()
  })
})
