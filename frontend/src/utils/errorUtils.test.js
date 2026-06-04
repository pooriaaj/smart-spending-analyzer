import { describe, expect, it } from 'vitest'

import { getApiErrorMessage, getApiSuccessMessage } from './errorUtils'

describe('errorUtils', () => {
  it('turns nested API validation errors into a readable message', () => {
    const message = getApiErrorMessage({
      response: {
        data: {
          detail: [
            { msg: 'Amount is required' },
            { msg: 'Amount is required' },
            { message: 'Category is required' },
          ],
        },
      },
    })

    expect(message).toBe('Amount is required Category is required')
  })

  it('uses a friendly network message when the server is unreachable', () => {
    const message = getApiErrorMessage(
      { request: {}, message: 'Network Error' },
      'Fallback message',
    )

    expect(message).toBe(
      'We could not reach the server. Please check your connection and try again.',
    )
  })

  it('includes request ids for server errors when available', () => {
    const message = getApiErrorMessage({
      response: {
        status: 500,
        data: {
          detail: 'Smart import failed. Please try a different file.',
          request_id: 'import-debug-123',
          stage: 'pdf_statement_parse',
        },
      },
    })

    expect(message).toBe(
      'Smart import failed. Please try a different file. Request ID: import-debug-123 Stage: pdf_statement_parse',
    )
  })

  it('reads success messages from API response data', () => {
    expect(getApiSuccessMessage({ message: 'Saved successfully' })).toBe(
      'Saved successfully',
    )
    expect(getApiSuccessMessage({}, 'Done')).toBe('Done')
  })
})
