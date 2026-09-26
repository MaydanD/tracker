import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { OwlState } from '../../api/owl'
import { recordSarcasm, type KeyValueStorage } from '../../utils/owlSession'
import { OWL_ASSETS, resolveOwlAsset } from './owlAssets'
import { OwlAssistantBanner } from './OwlAssistantBanner'

export function memoryStorage(): KeyValueStorage {
  const map = new Map<string, string>()
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value)
    },
  }
}

function owlState(overrides: Partial<OwlState> = {}): OwlState {
  return {
    owl_id: 'pending',
    asset_key: 'owl_pending',
    tone: 'cautionary',
    priority: 20,
    caption_line1: 'Эй, отметь привычку!',
    caption_line2: 'Осталось неотмеченными: 3 из 5.',
    dismissible: true,
    fingerprint: 'fp-pending',
    context: 'dashboard',
    fallback_line1: null,
    ...overrides,
  }
}

describe('OwlAssistantBanner', () => {
  it('renders the chosen asset with both caption lines', () => {
    render(<OwlAssistantBanner state={owlState()} storage={memoryStorage()} />)

    const banner = screen.getByTestId('owl-banner')
    expect(banner).toHaveAttribute('data-tone', 'cautionary')
    expect(screen.getByRole('img', { name: 'Сова-помощник' })).toHaveAttribute(
      'src',
      OWL_ASSETS.owl_pending,
    )
    expect(screen.getByText('Эй, отметь привычку!')).toBeInTheDocument()
    expect(screen.getByText('Осталось неотмеченными: 3 из 5.')).toBeInTheDocument()
  })

  it('renders nothing without a state', () => {
    const { container } = render(<OwlAssistantBanner state={null} storage={memoryStorage()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a dismiss control only for dismissible states', () => {
    const { unmount } = render(
      <OwlAssistantBanner state={owlState({ dismissible: true })} storage={memoryStorage()} />,
    )
    expect(screen.getByRole('button', { name: 'Скрыть' })).toBeInTheDocument()
    unmount()

    render(
      <OwlAssistantBanner
        state={owlState({ owl_id: 'failed', asset_key: 'owl_failed', tone: 'sarcastic', dismissible: false })}
        storage={memoryStorage()}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Скрыть' })).not.toBeInTheDocument()
  })

  it('keeps a dismissed state hidden for the session', async () => {
    const storage = memoryStorage()
    const { unmount } = render(<OwlAssistantBanner state={owlState()} storage={storage} />)

    fireEvent.click(screen.getByRole('button', { name: 'Скрыть' }))
    await waitFor(() => expect(screen.queryByTestId('owl-banner')).not.toBeInTheDocument())

    // Navigating away and back must not resurrect the same fingerprint.
    unmount()
    const { container } = render(<OwlAssistantBanner state={owlState()} storage={storage} />)
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('downgrades a sarcastic state while the cooldown is active', async () => {
    const storage = memoryStorage()
    recordSarcasm(Date.now(), storage)

    render(
      <OwlAssistantBanner
        state={owlState({
          owl_id: 'failed',
          asset_key: 'owl_failed',
          tone: 'sarcastic',
          caption_line1: 'У тебя есть порох или как?',
          fallback_line1: 'Отмечен провал привычки.',
          dismissible: false,
        })}
        storage={storage}
      />,
    )

    await waitFor(() => expect(screen.getByTestId('owl-banner')).toHaveAttribute('data-tone', 'cautionary'))
    expect(screen.getByText('Отмечен провал привычки.')).toBeInTheDocument()
    expect(screen.queryByText('У тебя есть порох или как?')).not.toBeInTheDocument()
  })

  it('shows a sarcastic state when no cooldown is active', () => {
    render(
      <OwlAssistantBanner
        state={owlState({
          owl_id: 'failed',
          asset_key: 'owl_failed',
          tone: 'sarcastic',
          caption_line1: 'У тебя есть порох или как?',
          fallback_line1: 'Отмечен провал привычки.',
          dismissible: false,
        })}
        storage={memoryStorage()}
      />,
    )
    expect(screen.getByTestId('owl-banner')).toHaveAttribute('data-tone', 'sarcastic')
    expect(screen.getByText('У тебя есть порох или как?')).toBeInTheDocument()
  })

  it('never leaks raw internal keys into the UI', () => {
    render(<OwlAssistantBanner state={owlState()} storage={memoryStorage()} />)
    const text = document.body.textContent ?? ''
    expect(text).not.toContain('owl_pending')
    expect(text).not.toContain('cautionary')
    expect(text).not.toContain('pending')
  })

  it('maps every asset key to a URL and falls back for unknown keys', () => {
    for (const value of Object.values(OWL_ASSETS)) {
      expect(typeof value).toBe('string')
      expect(value.length).toBeGreaterThan(0)
    }
    expect(resolveOwlAsset('owl_all_done')).toBe(OWL_ASSETS.owl_all_done)
    expect(resolveOwlAsset('unknown_state')).toBe(OWL_ASSETS.owl_insight)
  })
})
