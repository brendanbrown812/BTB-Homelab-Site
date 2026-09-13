export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export type CurrentUser = { id: string; username: string; display_name: string; role: "user" | "admin" };
export type LivePlayer = { player_id: string; name: string; position: string; team: string | null; injury_status: string | null; points: number | null; image_url: string | null };
export type LiveTeam = { roster_id: number; name: string; owner: string; record: string; score: number | null; avatar_url?: string | null; starters?: LivePlayer[]; bench?: LivePlayer[] };
export type LiveMatchup = { id: string; sleeper_matchup_id: number; team_a: LiveTeam; team_b: LiveTeam; winner_roster_id: number | null };
export type LiveWeek = {
  season: { id: string; year: number };
  week: { id: string; number: number; status: "open" | "locked" | "final"; lock_at: string; picks_public: boolean };
  matchups: LiveMatchup[];
  picks: Array<{ user_id: string; matchup_id: string; selected_roster_id: number | null; result: "win" | "loss" | "push" | null }>;
};
export type CurrentSubmissionStatus = {
  season: number;
  week: number;
  total_matchups: number;
  users: Array<{ user_id: string; display_name: string; submitted_picks: number }>;
};
export type PTGWriteup = {
  id: string;
  year: number;
  week: number;
  content_html: string;
  author: { id: string; display_name: string };
  updated_at: string;
  submitted_by_author?: boolean;
  is_published?: boolean;
  has_content?: boolean;
};
export type PTGWriteupList = {
  year: number;
  is_admin_view: boolean;
  available_years: number[];
  writeups: Array<Omit<PTGWriteup, "content_html">>;
};
export type PollOption = { id: string; text: string; position: number; voters: Array<{ id: string; display_name: string }> };
export type Poll = {
  id: string;
  question: string;
  description: string | null;
  selection_mode: "single" | "multiple";
  closes_at: string | null;
  closed_at: string | null;
  created_at: string;
  created_by: { id: string; display_name: string };
  is_open: boolean;
  options: PollOption[];
  current_user_option_ids: string[];
  not_voted: Array<{ id: string; display_name: string }>;
};
export type PollList = { is_admin: boolean; polls: Poll[] };

export function getToken() { return typeof window === "undefined" ? null : localStorage.getItem("btb_access_token"); }

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
  if (response.status === 401) {
    localStorage.removeItem("btb_access_token");
    throw new Error("AUTH_REQUIRED");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
