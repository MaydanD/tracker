import type { Direction } from '../../api/types'

/**
 * Russian description of a habit's direction.
 *
 * Direction is analytic metadata, not a moral verdict on the user's answer, so
 * it is surfaced only as an accessible name/tooltip — never as a large +/−/○
 * badge and never as red/green colouring of a value.
 */
export const DIRECTION_LABEL: Record<Direction, string> = {
  positive: 'чем больше, тем лучше',
  negative: 'чем больше, тем хуже',
  neutral: 'без оценки лучше/хуже',
}
