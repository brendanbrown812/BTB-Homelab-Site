type PredictionRecord = { wins: number; losses: number; pushes: number };

export function rankPredictionStandings<T extends PredictionRecord>(rows: T[]) {
  const sorted = [...rows].sort((a, b) => b.wins - a.wins || a.losses - b.losses || b.pushes - a.pushes);
  const recordKey = (row: PredictionRecord) => `${row.wins}:${row.losses}:${row.pushes}`;
  const groups = new Map<string, { rank: number; count: number }>();
  sorted.forEach((row, index) => {
    const key = recordKey(row);
    const group = groups.get(key);
    if (group) group.count++;
    else groups.set(key, { rank: index + 1, count: 1 });
  });
  return sorted.map(row => {
    const { rank, count } = groups.get(recordKey(row))!;
    return { ...row, rank, rankLabel: count > 1 ? `T${rank}` : String(rank), tied: count > 1 };
  });
}
