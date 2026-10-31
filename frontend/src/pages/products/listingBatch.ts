export async function runListingBatch<T>(
  items: T[],
  action: (item: T) => Promise<unknown>,
  onProgress?: (completed: number, total: number) => void,
): Promise<PromiseSettledResult<unknown>[]> {
  const settled: PromiseSettledResult<unknown>[] = [];
  for (let index = 0; index < items.length; index += 5) {
    const group = await Promise.allSettled(items.slice(index, index + 5).map(action));
    settled.push(...group);
    onProgress?.(settled.length, items.length);
  }
  return settled;
}

export function failedBatchIds<T extends { id: string }>(
  items: T[],
  results: PromiseSettledResult<unknown>[],
): string[] {
  return items.filter((_, index) => results[index]?.status !== "fulfilled").map((item) => item.id);
}
