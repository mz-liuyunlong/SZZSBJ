export function parseFollowLog(log: string | null | undefined): string[] {
 return (log ?? "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}
