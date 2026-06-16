// Maps the model's raw class output to a human-readable malocclusion class.
// The deployed checkpoint emits numeric class names ("0"/"1"/"2"); the local
// mock emits readable names already. Both are handled: numeric codes are mapped,
// anything already readable is passed through unchanged.
export function displayClass(raw: unknown): string {
  const value = String(raw ?? '').trim()
  const map: Record<string, string> = {
    '0': 'Class I',
    '1': 'Class II div 1',
    '2': 'Class III',
  }
  return map[value] || value || '—'
}
