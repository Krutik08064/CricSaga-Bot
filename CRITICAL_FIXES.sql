-- ============================================
-- CRITICAL FIXES - Run in Supabase SQL Editor
-- ============================================
-- Fixes for: registration_date column, connection pool, match counts
-- Run Date: January 13, 2026
-- ============================================

-- FIX 1: Add registration_date column (alias for registered_at)
-- This fixes: "column registration_date does not exist" error
ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Update existing rows to copy registered_at to registration_date
UPDATE users SET registration_date = registered_at WHERE registration_date IS NULL;

-- FIX 2: Kill idle connections to free up pool
-- Only kills current user's connections (no superuser needed)
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND state = 'idle'
  AND usename = current_user
  AND pid <> pg_backend_pid();

-- FIX 3: Remove double-counting trigger
-- This fixes: matches being counted twice
DROP TRIGGER IF EXISTS trigger_update_player_stats ON match_history;

-- FIX 4: Correct match counts (divide by 2 to fix double-counting)
UPDATE player_stats ps
SET matches_played = (
    SELECT COUNT(*) FROM match_history mh
    WHERE (mh.player1_id = ps.player_id OR mh.player2_id = ps.player_id)
) / 2;

-- FIX 5: Sync player_stats with career_stats
UPDATE player_stats ps
SET matches_played = cs.total_matches
FROM career_stats cs
WHERE ps.player_id = cs.player_id;

-- FIX 6: Ensure player_stats entries exist for all users
-- This fixes: foreign key constraint violation
INSERT INTO player_stats (player_id, user_id, matches_played, matches_won)
SELECT telegram_id, telegram_id, 0, 0
FROM users
WHERE telegram_id NOT IN (SELECT user_id FROM player_stats)
ON CONFLICT (player_id) DO NOTHING;

-- FIX 7: Ensure career_stats entries exist for all users
INSERT INTO career_stats (user_id, rating, rank_tier, total_matches, wins, losses)
SELECT telegram_id, 1000, 'Unranked', 0, 0, 0
FROM users
WHERE telegram_id NOT IN (SELECT user_id FROM career_stats)
ON CONFLICT (user_id) DO NOTHING;

-- Verification queries (check results)
SELECT 'Users with registration_date' AS check_name, COUNT(*) AS count 
FROM users WHERE registration_date IS NOT NULL
UNION ALL
SELECT 'Player stats entries', COUNT(*) FROM player_stats
UNION ALL
SELECT 'Career stats entries', COUNT(*) FROM career_stats
UNION ALL
SELECT 'Idle connections', COUNT(*) 
FROM pg_stat_activity 
WHERE state = 'idle' AND usename = current_user;
