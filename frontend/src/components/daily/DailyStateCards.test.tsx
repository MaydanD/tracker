/**
 * The «ч / мин» boxes of a duration card are local text, but the shared draft
 * is the source of truth: an outside change must reach them without remounting
 * the card, and the user's own typing must survive the echo of its own write.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useDurationParts } from './DailyStateCards'

function DurationHarness({
  value,
  onCommit,
}: {
  value: number | null
  onCommit: (total: number | null) => void
}) {
  const { hours, minutes, change } = useDurationParts(value, onCommit)
  return (
    <div>
      <label>
        часы
        <input value={hours} onChange={(event) => change(event.target.value, minutes)} />
      </label>
      <label>
        минуты
        <input value={minutes} onChange={(event) => change(hours, event.target.value)} />
      </label>
    </div>
  )
}

const hours = () => screen.getByLabelText('часы')
const minutes = () => screen.getByLabelText('минуты')

describe('useDurationParts', () => {
  it('shows an outside value that arrives without remounting', () => {
    const view = render(<DurationHarness value={null} onCommit={vi.fn()} />)
    expect(hours()).toHaveValue('')
    expect(minutes()).toHaveValue('')

    view.rerender(<DurationHarness value={450} onCommit={vi.fn()} />)
    expect(hours()).toHaveValue('7')
    expect(minutes()).toHaveValue('30')

    view.rerender(<DurationHarness value={90} onCommit={vi.fn()} />)
    expect(hours()).toHaveValue('1')
    expect(minutes()).toHaveValue('30')
  })

  it('empties the boxes when the draft value is cleared from outside', () => {
    const view = render(<DurationHarness value={450} onCommit={vi.fn()} />)
    expect(hours()).toHaveValue('7')

    view.rerender(<DurationHarness value={null} onCommit={vi.fn()} />)
    expect(hours()).toHaveValue('')
    expect(minutes()).toHaveValue('')
  })

  it('keeps exactly what the user typed when their own value comes back', () => {
    const commit = vi.fn()
    const view = render(<DurationHarness value={null} onCommit={commit} />)

    fireEvent.change(hours(), { target: { value: '07' } })
    fireEvent.change(minutes(), { target: { value: '05' } })
    expect(commit).toHaveBeenLastCalledWith(425)

    // The store echoes the committed value back: it must not reformat the text
    // the user is still looking at.
    view.rerender(<DurationHarness value={425} onCommit={commit} />)
    expect(hours()).toHaveValue('07')
    expect(minutes()).toHaveValue('05')
  })

  it('commits once per edit and never re-commits on an echo', () => {
    const commit = vi.fn()
    const view = render(<DurationHarness value={null} onCommit={commit} />)

    fireEvent.change(minutes(), { target: { value: '30' } })
    expect(commit).toHaveBeenCalledTimes(1)
    expect(commit).toHaveBeenLastCalledWith(30)

    view.rerender(<DurationHarness value={30} onCommit={commit} />)
    expect(commit).toHaveBeenCalledTimes(1)

    // Clearing both boxes is an explicit "no value", not zero.
    fireEvent.change(minutes(), { target: { value: '' } })
    expect(commit).toHaveBeenLastCalledWith(null)
    // A zero box is a real zero, not "no value".
    fireEvent.change(hours(), { target: { value: '0' } })
    expect(commit).toHaveBeenLastCalledWith(0)
    expect(commit).toHaveBeenCalledTimes(3)
  })
})
