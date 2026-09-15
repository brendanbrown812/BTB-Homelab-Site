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
  due_date?: string | null;
  is_published?: boolean;
  has_content?: boolean;
};
export type PTGWriteupList = {
  year: number;
  is_admin_view: boolean;
  available_years: number[];
  writeups: Array<Omit<PTGWriteup, "content_html">>;
};
export type UpcomingWriteup = { id: string; year: number; week: number; due_date: string; days_remaining: number };
export type PTGComment = {
  id: string;
  parent_id: string | null;
  content: string | null;
  is_deleted: boolean;
  author: { id: string; display_name: string; is_admin: boolean } | null;
  created_at: string;
  edited_at: string | null;
};
export type PTGCommentThread = { current_user_id: string; is_admin: boolean; comments: PTGComment[] };
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
  notification_status?: "sent" | "not_configured" | "failed" | "bypassed";
};
export type PollList = { is_admin: boolean; polls: Poll[] };
export type LeagueManagerAlias = { id: string; provider: "notion_name" | "sleeper_user_id"; external_value: string };
export type LeagueManager = { id: string; user_id: string | null; display_name: string; biography: string; is_active: boolean; aliases: LeagueManagerAlias[] };
export type LeagueSeasonTeam = { id: string; manager_id: string; team_name: string; sleeper_user_id: string | null; roster_id: number | null };
export type LeaguePlacement = { id: string; manager_id: string; calculated_placement: number | null; override_placement: number | null };
export type LeaguePunishment = { id: string; manager_id: string; title: string };
export type LeagueSeasonFact = { id: string; label: string; value: string; display_order: number };
export type LeagueWeeklyHighlight = { id: string; week: number; category: string; manager_id: string | null; player_id: string | null; player_name: string | null; value: number | null };
export type LeagueImportRun = { id: string; season_id: string | null; source: "notion" | "sleeper" | "manual"; status: "running" | "succeeded" | "failed" | "needs_attention"; counts: Record<string, unknown>; error_details: string | null; started_at: string; finished_at: string | null };
export type ManagedLeagueSeason = {
  id: string;
  year: number;
  platform: "espn" | "sleeper";
  sleeper_league_id: string | null;
  is_active: boolean;
  teams: LeagueSeasonTeam[];
  placements: LeaguePlacement[];
  punishment: LeaguePunishment | null;
  facts: LeagueSeasonFact[];
  highlights: LeagueWeeklyHighlight[];
};
export type LeagueHistoryAdminState = {
  users: Array<{ id: string; username: string; display_name: string; is_active: boolean }>;
  managers: LeagueManager[];
  seasons: ManagedLeagueSeason[];
  import_runs: LeagueImportRun[];
};
export type ManagerSelfProfile = { manager: { id: string; display_name: string; biography: string } | null };
export type LeagueCareerRecord = { wins: number; losses: number; ties: number; points_for: number; points_against: number };
export type PublicLeagueManager = { id: string; display_name: string; biography: string; is_active: boolean; seasons_played: number; championships: number; biggest_losers: number; team_names: string[]; latest_team_name: string | null; career: LeagueCareerRecord; transaction_total: number; punishment_total: number };
export type HeadToHeadManager = { id: string; display_name: string; is_active: boolean };
export type HeadToHeadSide = { id: string; display_name: string; wins: number; points_for: number; average_score: number };
export type HeadToHeadGame = { id: string; season_id: string; year: number; week: number; week_end: number | null; team_a_name: string; team_b_name: string; score_a: number; score_b: number; winner_id: string | null; margin: number; source: "notion" | "sleeper" | "manual" };
export type PublicHeadToHead = {
  managers: HeadToHeadManager[];
  comparison: { manager_a: HeadToHeadSide; manager_b: HeadToHeadSide; ties: number; total_matchups: number; games: HeadToHeadGame[] } | null;
};
export type PublicManagerDetail = {
  manager: Pick<PublicLeagueManager, "id" | "display_name" | "biography" | "is_active">;
  seasons: Array<{ season_id: string; year: number; platform: "espn" | "sleeper"; team_name: string; placement: number | null; placement_source: "calculated" | "overridden" | "unavailable" }>;
  championships: number;
  biggest_losers: number;
  career: LeagueCareerRecord;
  transactions: { total: number; by_type: Record<string, number> };
  punishments: Array<{ season_id: string; year: number; title: string }>;
  current_roster: { season_year: number; team_name: string; players: LivePlayer[]; error: string | null } | null;
};
export type PublicLeagueSeason = { id: string; year: number; platform: "espn" | "sleeper"; is_active: boolean; manager_count: number; matchup_count: number; placement_count: number; sources: Array<"notion" | "sleeper" | "manual"> };
export type PublicSeasonDetail = {
  season: Pick<PublicLeagueSeason, "id" | "year" | "platform" | "is_active" | "sources">;
  placements: Array<{ manager_id: string; manager_name: string; team_name: string; placement: number | null; placement_source: "calculated" | "overridden" | "unavailable" }>;
  standings: Array<{ manager_id: string; manager_name: string; team_name: string; placement: number | null; placement_source: "calculated" | "overridden" | "unavailable" } & LeagueCareerRecord>;
  weekly_results: Array<{ id: string; week: number; week_end: number | null; week_label: string | null; manager_a_id: string; manager_b_id: string; team_a_name: string; team_b_name: string; score_a: number | null; score_b: number | null; source: "notion" | "sleeper" | "manual" }>;
  awards: Array<{ id: string; week: number; category: string; manager_id: string | null; manager_name: string | null; player_id: string | null; player_name: string | null; player_image_url: string | null; value: number | null; detail: string | null; source: "calculated" | "manual" }>;
  facts: Array<{ id: string; label: string; value: string; source: "manual" }>;
  punishment: { manager_id: string; manager_name: string; title: string; source: "manual" } | null;
};
export type PublicTransactionPlayer = { player_id: string; name: string; position: string | null; team: string | null; image_url: string | null };
export type PublicTransactionParticipant = { manager_id: string; manager_name: string; roster_id: number };
export type PublicTransactionSide = PublicTransactionParticipant & {
  adds: PublicTransactionPlayer[];
  drops: PublicTransactionPlayer[];
  draft_picks_received: Array<{ season: number; round: number; original_roster_id: number; original_manager_name: string }>;
  draft_picks_sent: Array<{ season: number; round: number }>;
  faab_received: number;
  faab_sent: number;
};
export type PublicLeagueTransaction = {
  id: string;
  external_id: string;
  season: number;
  week: number;
  transaction_type: string;
  status: string;
  occurred_at: string;
  participants: PublicTransactionParticipant[];
  sides: PublicTransactionSide[];
  adds: PublicTransactionPlayer[];
  drops: PublicTransactionPlayer[];
  bid_amount: number | null;
};
export type PublicTransactionResponse = {
  items: PublicLeagueTransaction[];
  options: {
    seasons: number[];
    managers: Array<{ id: string; display_name: string }>;
    transaction_types: string[];
    statuses: string[];
  };
};
export type PublicLeagueRecordEntry = {
  manager_id: string;
  manager_name: string;
  value: number;
  detail: string;
  season_id: string | null;
  year: number | null;
  week: number | null;
};
export type PublicLeagueRecord = {
  key: string;
  label: string;
  category: string;
  tied: boolean;
  entries: PublicLeagueRecordEntry[];
};
export type PublicLeagueOverview = {
  champion: { season_id: string; year: number; manager_id: string; manager_name: string; placement: number; source: string } | null;
  podium: Array<{ season_id: string; year: number; manager_id: string; manager_name: string; placement: number; source: string }>;
  current_managers: Array<{ id: string; display_name: string; team_name: string | null }>;
  latest_trades: PublicOverviewTransaction[];
  latest_waivers: PublicOverviewTransaction[];
  headline_records: PublicLeagueRecord[];
  recent_highlights: Array<PublicSeasonDetail["awards"][number] & { season_id: string; year: number }>;
  punishment: { season_id: string; year: number; manager_id: string; manager_name: string; title: string } | null;
};
export type PublicOverviewTransaction = {
  id: string;
  season: number | null;
  week: number;
  transaction_type: string;
  status: string;
  occurred_at: string;
  manager_names: string[];
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
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}
