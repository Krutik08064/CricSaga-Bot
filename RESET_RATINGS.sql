-- RESET ALL STATS (CAREER + PROFILE) TO DEFAULT
-- WARNING: This will reset all player ratings, matches, and profile stats to 0

-- Step 1: Reset career stats (ratings, matches, streaks)
UPDATE career_stats
SET rating = 1000,
    rank_tier = 'Gold I',
    total_matches = 0,
    wins = 0,
    losses = 0,
    current_streak = 0,
    streak_type = 'none',
    highest_rating = 1000,
    updated_at = CURRENT_TIMESTAMP;

-- Step 2: Reset profile stats (runs, wickets, etc.)
UPDATE player_stats
SET matches_played = 0,
    matches_won = 0,
    total_runs_scored = 0,
    total_wickets_taken = 0,
    total_balls_faced = 0,
    highest_score = 0,
    total_boundaries = 0,
    total_sixes = 0,
    dot_balls = 0,
    fifties = 0,
    hundreds = 0,
    best_bowling = '',
    last_five_scores = '[]';

-- Step 3: Delete all ranked match history (optional - uncomment if needed)
-- DELETE FROM ranked_matches;

-- Verify reset
SELECT 'Career Stats' as table_name, 
       COUNT(*) as total_users, 
       AVG(rating) as avg_rating, 
       SUM(total_matches) as total_matches
FROM career_stats
UNION ALL
SELECT 'Profile Stats', 
       COUNT(*), 
       AVG(total_runs_scored), 
       SUM(matches_played)
FROM player_stats;
