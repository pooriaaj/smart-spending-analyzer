import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import AccountSelector from './AccountSelector'

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}))

const accounts = [
  { id: 7, name: 'Everyday', type: 'checking' },
  { id: 9, name: 'Savings Bucket', type: 'savings' },
]

function renderAccountSelector(props = {}) {
  return render(
    <LanguageProvider>
      <AccountSelector label="Account scope" {...props} />
    </LanguageProvider>,
  )
}

describe('AccountSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    api.get.mockResolvedValue({ data: accounts })
  })

  it('loads accounts and keeps the all-accounts option when allowed', async () => {
    const onChange = vi.fn()
    renderAccountSelector({ onChange })

    expect(screen.getByRole('combobox', { name: 'Account scope' })).toHaveValue('all')
    expect(await screen.findByRole('option', { name: 'Everyday (Chequing)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Savings Bucket (Savings)' })).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/accounts/', {
      params: { include_stats: false },
    })
    expect(localStorage.getItem('selectedAccountId')).toBe('all')
    expect(onChange).toHaveBeenCalledWith('all')
  })

  it('persists a user-selected account', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderAccountSelector({ onChange })

    await screen.findByRole('option', { name: 'Everyday (Chequing)' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Account scope' }), '9')

    expect(screen.getByRole('combobox', { name: 'Account scope' })).toHaveValue('9')
    expect(localStorage.getItem('selectedAccountId')).toBe('9')
    expect(onChange).toHaveBeenLastCalledWith('9')
  })

  it('uses the first loaded account when all-accounts is not allowed', async () => {
    localStorage.setItem('selectedAccountId', 'all')
    const onChange = vi.fn()

    renderAccountSelector({ allowAll: false, onChange })

    expect(screen.getByRole('combobox', { name: 'Account scope' })).toHaveValue('')
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'Account scope' })).toHaveValue('7')
    })
    expect(screen.queryByRole('option', { name: 'All Accounts' })).not.toBeInTheDocument()
    expect(localStorage.getItem('selectedAccountId')).toBe('7')
    expect(onChange).toHaveBeenLastCalledWith('7')
  })

  it('can notify selection changes without persisting them', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    localStorage.setItem('selectedAccountId', 'all')

    renderAccountSelector({ onChange, persistSelection: false })

    await screen.findByRole('option', { name: 'Everyday (Chequing)' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Account scope' }), '7')

    expect(onChange).toHaveBeenLastCalledWith('7')
    expect(localStorage.getItem('selectedAccountId')).toBe('all')
  })
})
