// Mirrors the FastAPI Pydantic schemas (backend/app/schemas/*).
export type Role = "user" | "admin";
export type GameRole = "dps" | "healer" | "tank";
export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface UserOut {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  locale: string;
  created_at: string;
  last_login_at: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface PublicConfig {
  app_name: string;
  supported_locales: string[];
  allow_registration: boolean;
}

export interface GameSpec {
  slug: string;
  name_en: string;
  name_de: string;
  role: GameRole;
  wcl_spec_id: number;
}

export interface GameClass {
  slug: string;
  name_en: string;
  name_de: string;
  color_hex: string;
  specs: GameSpec[];
}

export interface ReportPlayerCast {
  ability_id: number;
  ability_name: string;
  casts: number;
  hits: number;
  total: number;
  icon: string | null;
}

export interface ReportPlayerGear {
  slot: number;
  item_id: number;
  item_level: number | null;
  item_quality: number | null;
  name: string;
  icon: string | null;
  enchant_id: number | null;
  gem_ids: number[];
  bonus_ids: number[];
}

export interface ReportPlayer {
  id: string;
  name: string;
  server: string;
  class_slug: string;
  spec_slug: string;
  role: GameRole;
  item_level: number | null;
  dps: number | null;
  hps: number | null;
  damage_done: number;
  healing_done: number;
  deaths: number;
  talents_loadout: string | null;
  casts: ReportPlayerCast[];
  gear: ReportPlayerGear[];
}

export interface ReportFight {
  id: string;
  fight_id: number;
  encounter_id: number | null;
  name: string;
  difficulty: number | null;
  keystone_level: number | null;
  is_kill: boolean;
  boss_percentage: number | null;
  duration_ms: number;
  start_time: string;
  players: ReportPlayer[];
}

export interface Report {
  id: string;
  wcl_code: string;
  title: string;
  zone_id: number | null;
  zone_name: string;
  region: string;
  game_version: string;
  start_time: string;
  end_time: string;
  fights: ReportFight[];
}

export interface ReportSummary {
  id: string;
  wcl_code: string;
  title: string;
  zone_name: string;
  start_time: string;
  end_time: string;
}

export interface AnalysisFinding {
  severity: Severity;
  title: string;
  detail: string;
  estimated_loss_pct: number | null;
  category:
    | "rotation"
    | "cooldowns"
    | "stats"
    | "talents"
    | "gear"
    | "trinkets"
    | "consumables"
    | "mechanics"
    | "other";
  related_spell_ids: number[];
  related_item_ids: number[];
}

export interface AnalysisStructured {
  headline: string;
  overall_score: number;
  role_focus: GameRole;
  strengths: string[];
  findings: AnalysisFinding[];
  rotation_summary: string;
  cooldown_usage_summary: string;
  stat_recommendations: string;
  talent_recommendations: string;
  gear_and_trinket_notes: string;
  comparison_to_top_logs: string;
}

export interface Analysis {
  id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  locale: string;
  provider: string;
  model: string;
  summary: string;
  structured: AnalysisStructured | Record<string, never>;
  error: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface TopLog {
  id: string;
  spec_slug: string;
  encounter_id: number;
  encounter_name: string;
  difficulty: number | null;
  metric: "dps" | "hps";
  rank: number;
  amount: number;
  item_level: number | null;
  duration_ms: number | null;
  character_name: string;
  server: string;
  region: string;
  wcl_report_code: string;
  wcl_fight_id: number;
  recorded_at: string;
}

export interface ApiError {
  error: { code: string; message: string; details?: unknown };
}

export interface Invite {
  id: string;
  email: string;
  expires_at: string;
  accepted_at: string | null;
  revoked: boolean;
  created_at: string;
}

export interface AdminSettings {
  allow_registration: boolean;
  ai_provider: string;
  ai_model: string;
}
