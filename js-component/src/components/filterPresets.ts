/**
 * Filter presets: ready-made filters listed at the top of a table's filter
 * dialog, each switched on and off with a check box. A preset that is on keeps
 * only the rows matching every one of its conditions.
 *
 * Shared by the general table (`Table(filter_presets=...)`, filtered in Python)
 * and the fragment table of the sequence view (filtered in the browser).
 */

export type PresetOp = '==' | '!=' | '<=' | '>=' | '<' | '>' | 'in' | 'not in'

export interface PresetCondition {
  column: string
  op: PresetOp
  value: unknown
}

export interface FilterPreset {
  id: string
  label: string
  help?: string
  /** Every condition must hold for a row to stay */
  filters: PresetCondition[]
  /** On until the viewer switches it (default: off) */
  default?: boolean
}

/** Whether `row` passes one condition of a preset. */
export function conditionMatches(row: Record<string, unknown>, condition: PresetCondition): boolean {
  const cell = row[condition.column]
  const value = condition.value
  switch (condition.op) {
    case '==':
      return cell === value
    case '!=':
      return cell !== value
    case '<=':
      return typeof cell === 'number' && cell <= (value as number)
    case '>=':
      return typeof cell === 'number' && cell >= (value as number)
    case '<':
      return typeof cell === 'number' && cell < (value as number)
    case '>':
      return typeof cell === 'number' && cell > (value as number)
    case 'in':
      return Array.isArray(value) && value.includes(cell)
    case 'not in':
      return !Array.isArray(value) || !value.includes(cell)
    default:
      return true
  }
}

/** Whether `row` passes every condition of `preset`. */
export function presetMatches(row: Record<string, unknown>, preset: FilterPreset): boolean {
  return preset.filters.every((condition) => conditionMatches(row, condition))
}

/** The columns a set of presets reads, so a table keeps them in its rows. */
export function presetColumns(presets: FilterPreset[]): string[] {
  return [...new Set(presets.flatMap((preset) => preset.filters.map((c) => c.column)))]
}

/** A filter the viewer set themselves (a column filter or the search), listed with the presets. */
export interface UserFilterEntry {
  key: string
  label: string
  /** Remove the filter (its check box was unticked) */
  remove: () => void
}

/**
 * Draw the "Filters" section of a filter dialog into `content`: one check box
 * per preset, with its help below it, then one ticked check box per filter the
 * viewer set (column filters, search), which removes that filter when
 * unticked. Nothing is drawn while there is neither.
 */
export function renderPresetSection(
  doc: Document,
  content: HTMLElement,
  presets: FilterPreset[],
  isActive: (preset: FilterPreset) => boolean,
  setActive: (preset: FilterPreset, active: boolean) => void,
  userFilters: UserFilterEntry[] = [],
): void {
  if (presets.length === 0 && userFilters.length === 0) return
  const section = doc.createElement('div')
  section.className = 'filter-presets'
  section.style.cssText = `
    background-color: white;
    border-radius: 4px;
    border: 1px solid #e0e0e0;
    padding: 16px;
    margin-bottom: 24px;
  `
  const heading = doc.createElement('h6')
  heading.textContent = 'Filters:'
  heading.style.cssText = 'color: #333; margin: 0 0 12px 0; font-size: 16px; font-weight: 500;'
  section.appendChild(heading)

  const row = (text: string, checked: boolean, onChange: (checked: boolean) => void, help?: string) => {
    const label = doc.createElement('label')
    label.style.cssText =
      'display: flex; align-items: center; gap: 8px; color: #333; font-size: 14px; cursor: pointer; margin-bottom: 4px;'
    if (help) label.title = help
    const box = doc.createElement('input')
    box.type = 'checkbox'
    box.checked = checked
    box.addEventListener('change', () => onChange(box.checked))
    const span = doc.createElement('span')
    span.textContent = text
    label.appendChild(box)
    label.appendChild(span)
    section.appendChild(label)
    if (help) {
      const note = doc.createElement('div')
      note.textContent = help
      note.style.cssText = 'color: #666; font-size: 12px; margin: 0 0 8px 26px;'
      section.appendChild(note)
    }
  }

  for (const preset of presets) {
    row(preset.label, isActive(preset), (checked) => setActive(preset, checked), preset.help)
  }
  if (userFilters.length > 0) {
    const sub = doc.createElement('div')
    sub.textContent = presets.length > 0 ? 'Set by you (untick to remove):' : 'Untick to remove:'
    sub.style.cssText = `color: #666; font-size: 12px; margin: ${presets.length > 0 ? '12px' : '0'} 0 6px 0;`
    section.appendChild(sub)
    for (const entry of userFilters) {
      row(entry.label, true, (checked) => {
        if (!checked) entry.remove()
      })
    }
  }
  content.appendChild(section)
}
