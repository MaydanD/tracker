import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest runs without globals, so React Testing Library's automatic cleanup
// between tests is not installed for us.
afterEach(() => {
  cleanup()
})
