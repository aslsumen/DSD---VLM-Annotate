/** Schedule the next refresh only after the current load settles. */
export function schedulePoll(
  { active, loading, status }: { active: boolean; loading: boolean; status?: number },
  delay: number,
  reload: () => void,
  sessionExpired?: () => void,
): (() => void) | undefined {
  if (status === 401) {
    sessionExpired?.();
    return undefined;
  }
  if (!active || loading) return undefined;

  const timer = setTimeout(reload, delay);
  return () => clearTimeout(timer);
}
