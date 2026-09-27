import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { stubRecords } from '../test/recordsFixture'
import { RecordsPage } from './RecordsPage'

describe('RecordsPage', () => {
  it('shows habit-specific streak and consistency records without achievements', async () => {
    stubRecords()
    render(<RecordsPage />)

    expect(await screen.findByRole('heading', { name: 'Рекорды по привычкам' })).toBeInTheDocument()
    const streak = screen.getByText('Лучшая серия').closest('article') as HTMLElement
    expect(within(streak).getByText('28 дней')).toBeInTheDocument()
    expect(within(streak).getByText('Чтение')).toBeInTheDocument()
    expect(within(streak).getByText('12.08.2026 — 08.09.2026')).toBeInTheDocument()

    const habitRecord = screen.getByText('Стабильность привычки').closest('article') as HTMLElement
    expect(within(habitRecord).getByText('94%')).toBeInTheDocument()
    expect(within(habitRecord).getByText('Август 2026')).toBeInTheDocument()
    expect(screen.queryByText('Достижения')).not.toBeInTheDocument()
    expect(screen.queryByText('Месяц без отрыва')).not.toBeInTheDocument()
  })
})
