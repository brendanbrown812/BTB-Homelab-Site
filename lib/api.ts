export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export type CurrentUser = { id: string; username: string; display_name: string; role: "user" | "admin" };
export type LivePlayer = { player_id: string; name: string; position: string; team: string | null; injury_status: string | null; points: number | null };
export type LiveTeam = { roster_id: number; name: string; owner: string; record: string; score: number | null; starters?: LivePlayer[]; bench?: LivePlayer[] };
export type LiveMatchup = { id: string; sleeper_matchup_id: number; team_a: LiveTeam; team_b: LiveTeam; winner_roster_id: number | null };
export type LiveWeek = {
  season: { id: string; year: number };
  week: { id: string; number: number; status: "open" | "locked" | "final"; lock_at: string; picks_public: boolean };
  matchups: LiveMatchup[];
  picks: Array<{ user_id: string; matchup_id: string; selected_roster_id: number | null; result: "win" | "loss" | "push" | null }>;
};

export function getToken() { return typeof window === "undefined" ? null : localStorage.getItem("btb_access_token"); }

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
  if (response.status === 401) {
    localStorage.removeItem("btb_access_token");
    throw new Error("AUTH_REQUIRED");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json();
}
