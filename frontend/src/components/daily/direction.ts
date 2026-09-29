import type { Direction } from '../../api/types'

/**
 * Russian description of a habit's direction.
 *
 * Direction is analytic metadata, not a moral verdict on the user's answer, so
 * it is surfaced only as an accessible name/tooltip — never as a large +/−/○
 * badge and never as red/green colouring of a value. The words match the habit
 * editor, so the user recognises the setting they chose.
 */
export const DIRECTION_LABEL: Record<Direction, string> = {
  positive: 'Полезная — больше значит лучше',
  negative: 'Вредная — меньше значит лучше',
  neutral: 'Нейтральная — просто отслеживание',
}
