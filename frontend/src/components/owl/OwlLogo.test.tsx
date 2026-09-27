import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import type { OwlState } from '../../api/owl'
import { OwlLogo } from './OwlLogo'
import { OWL_ASSETS } from './owlAssets'
import { resetOwlStore, setOwl } from './owlStore'

function state(overrides: Partial<OwlState> = {}): OwlState {
  return {
    owl_id: 'all_completed',
    asset_key: 'owl_all_done',
    tone: 'celebratory',
    priority: 70,
    caption_line1: 'Ну вот. Можешь жить.',
    caption_line2: 'Все привычки выполнены.',
    dismissible: true,
    fingerprint: 'fp-all-done',
    context: 'dashboard',
    fallback_line1: null,
    ...overrides,
  }
}

function renderLogo() {
  return render(
    <MemoryRouter>
      <OwlLogo />
    </MemoryRouter>,
  )
}

describe('OwlLogo', () => {
  afterEach(() => resetOwlStore())

  it('links back to the main screen', () => {
    setOwl(state())
    renderLogo()
    expect(screen.getByRole('link', { name: /на главную/i })).toHaveAttribute('href', '/')
  })

  it('shows the current Owl asset published by a page', () => {
    setOwl(state())
    renderLogo()
    expect(screen.getByRole('presentation')).toHaveAttribute('src', OWL_ASSETS.owl_all_done)
  })

  it('falls back to the neutral pending owl before any state is known', () => {
    renderLogo()
    expect(screen.getByRole('presentation')).toHaveAttribute('src', OWL_ASSETS.owl_pending)
  })
})
