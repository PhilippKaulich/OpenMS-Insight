/**
 * The value a clicked peak writes to the state.
 *
 * Columns arrive as 32-bit floats, so 341.3387 reaches the browser as
 * 341.33868408203125. A value that is a 32-bit float is written as the
 * shortest decimal that reads back as the same 32-bit float (341.3387);
 * any other value is written as it is.
 */
export function pickedValue(x: number): number {
  if (!Number.isFinite(x) || Math.fround(x) !== x) return x
  for (let digits = 1; digits <= 9; digits++) {
    const shorter = Number(x.toPrecision(digits))
    if (Math.fround(shorter) === x) return shorter
  }
  return x
}

/** `pickedValue` for numbers; any other value (an id string, null) as it is. */
export function selectedValue(value: unknown): unknown {
  return typeof value === 'number' ? pickedValue(value) : value
}

/**
 * Whether a column value is the selected one. A selected number matches the
 * 32-bit float it rounds to, so `341.3387` finds the peak sent as
 * 341.33868408203125.
 */
export function sameValue(column: unknown, selected: unknown): boolean {
  if (column === selected) return true
  return typeof column === 'number' && typeof selected === 'number' && Math.fround(selected) === column
}
