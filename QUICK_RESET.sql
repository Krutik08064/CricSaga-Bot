-- ============================================
-- QUICK RESET - Fast reset without clearing history
-- ============================================
-- This only resets ratings and match counts, keeps other stats
-- Run Date: January 13, 2026
-- ============================================

-- Reset only ratings and match counts (FAST)
UPDATE career_stats
SET rating = 1000,
    rank_tier = 'Unranked',
    total_matches = 0,
    wins = 0,
    losses = 0,
    current_streak = 0,
    streak_type = 'none',
    highest_rating = 1000;

-- Reset only match counts in player_stats (FAST)
UPDATE player_stats
SET matches_played = 0,
    matches_won = 0;

-- Verification
SELECT 'Career stats reset' AS status, COUNT(*) AS count FROM career_stats WHERE rating = 1000;
SELECT 'Player stats reset' AS status, COUNT(*) AS count FROM player_stats WHERE matches_played = 0;
