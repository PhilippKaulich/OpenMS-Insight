/**
 * The previous / next buttons of a plot's `stepper` (see core/stepper.py).
 *
 * Python sends the current value of the stepped filter, its position and its
 * neighbours with every render. A click writes the neighbour to the filter's
 * identifier; until the next render brings the new neighbours, further clicks
 * wait, so a quick double click steps once rather than twice from stale data.
 */

import { ICONS, type PlotTool } from '@/utils/plotTools'

export interface StepperArgs {
  identifier: string
  label: string
  value: unknown
  /** Position of `value` among the sorted values (null: not among them). */
  index: number | null
  count: number
  prev: unknown
  next: unknown
}

function show(value: unknown): string {
  if (value === null || value === undefined) return '–'
  if (typeof value === 'number' && !Number.isInteger(value)) return String(Number(value.toPrecision(6)))
  return String(value)
}

/**
 * The two toolbar buttons: `◀ frame 12` and `▶`. `current` is the value in
 * the browser's state now; `select` writes a value to the identifier.
 */
export function stepperTools(
  stepper: StepperArgs | undefined,
  current: unknown,
  select: (identifier: string, value: unknown) => void,
): PlotTool[] {
  if (!stepper || stepper.count === 0) return []
  const { identifier, label, index, count, prev, next } = stepper
  // A click sent, its render not here yet
  const waiting = current !== undefined && current !== stepper.value
  const position = index === null ? `${count} values` : `${index + 1} of ${count}`
  const shown = show(waiting ? current : stepper.value)
  const step = (value: unknown) => () => {
    if (waiting || value === null || value === undefined) return
    select(identifier, value)
  }
  return [
    {
      id: 'stepper-previous',
      group: 'view',
      icon: ICONS.previous,
      label: `Previous ${label}`,
      short: `${label} ${shown}`,
      help: prev === null || prev === undefined ? `${position}; this is the first` : `${position}; go to ${show(prev)}`,
      run: step(prev),
    },
    {
      id: 'stepper-next',
      group: 'view',
      icon: ICONS.next,
      label: `Next ${label}`,
      help: next === null || next === undefined ? `${position}; this is the last` : `${position}; go to ${show(next)}`,
      run: step(next),
    },
  ]
}
