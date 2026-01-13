-- ============================================
-- RESET ALL PLAYER STATS - Run in Supabase
-- ============================================
-- This will reset all player ratings and stats to default values
-- Run Date: January 13, 2026
-- ============================================

-- Reset career_stats to default
UPDATE career_stats
SET rating = 1000,
    rank_tier = 'Unranked',
    total_matches = 0,
    wins = 0,
    losses = 0,
    current_streak = 0,
    streak_type = 'none',
    highest_rating = 1000,
    trust_score = 50,
    rating_suspended = FALSE,
    account_flagged = FALSE;

-- Reset player_stats to default
UPDATE player_stats
SET matches_played = 0,
    matches_won = 0,
    total_runs = 0,
    total_wickets = 0,
    total_balls_faced = 0,
    highest_score = 0,
    best_bowling = '0/0',
    total_fours = 0,
    total_sixes = 0,
    fifties = 0,
    hundreds = 0,
    five_wicket_hauls = 0,
    hat_tricks = 0,
    dot_balls = 0,
    average = 0,
    strike_rate = 0,
    economy_rate = 0,
    avg_runs_per_match = 0,
    avg_wickets_per_match = 0,
    last_five_scores = '[]',
    total_runs_scored = 0,
    total_wickets_taken = 0,
    total_boundaries = 0;

-- Verification
SELECT 'Career stats reset' AS status, COUNT(*) AS count FROM career_stats WHERE rating = 1000;
SELECT 'Player stats reset' AS status, COUNT(*) AS count FROM player_stats WHERE matches_played = 0;
