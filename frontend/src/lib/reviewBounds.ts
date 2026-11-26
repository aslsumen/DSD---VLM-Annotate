// The annotation API persists seconds to three decimal places.
export function reviewSeconds(text: string): number | null {
  const decimal = text.trim().replace(",", ".");
  if (!/^(?:\d+(?:\.\d{0,3}0*)?|\.\d{1,3}0*)$/.test(decimal)) return null;
  const seconds = Number(decimal);
  return Number.isFinite(seconds) ? seconds : null;
}

export function reviewInterval(startText: string, endText: string, duration: number):
  { start: number; end: number } | { error: string } {
  const start = reviewSeconds(startText);
  const end = reviewSeconds(endText);
  if (start === null || end === null) {
    return { error: "Enter non-negative seconds with up to three decimal places." };
  }
  if (end <= start) return { error: "The end must be after the start." };
  if (end > duration) return { error: "The interval must be within the video." };
  return { start, end };
}
