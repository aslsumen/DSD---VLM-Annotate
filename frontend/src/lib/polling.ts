/** Schedule the next refresh only after the current load settles. */
export function schedulePoll(
  { active, loading, status }: { active: boolean; loading: boolean; status?: number },
  delay: number,
  reload: () => void,
): (() => void) | undefined {
  if (!active || loading || status === 401 || status === 403) return undefined;

  const timer = setTimeout(reload, delay);
  return () => clearTimeout(timer);
}
