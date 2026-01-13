-- Fix: Remove automatic match counting trigger to prevent double counting
-- The bot code already handles match counting in career_stats manually

-- STEP 1: Kill only YOUR idle connections (no superuser needed)
-- This will only kill connections belonging to your user
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state = 'idle'
  AND usename = current_user
  AND state_change < NOW() - INTERVAL '5 minutes';

-- STEP 2: Drop the problematic trigger
DROP TRIGGER IF EXISTS trigger_update_player_stats ON scorecards;

-- Drop the function since it's no longer needed
DROP FUNCTION IF EXISTS update_player_stats_after_match();

-- STEP 3: Correct match counts (divide by 2 since they were double-counted)
-- Update both career_stats and player_stats
UPDATE career_stats
SET total_matches = GREATEST(1, total_matches / 2),
    wins = GREATEST(0, wins / 2),
    losses = GREATEST(0, losses / 2);

UPDATE player_stats
SET matches_played = GREATEST(1, matches_played / 2),
    matches_won = GREATEST(0, matches_won / 2);

-- STEP 4: Sync player_stats with career_stats
UPDATE player_stats ps
SET matches_played = cs.total_matches,
    matches_won = cs.wins
FROM career_stats cs
WHERE ps.user_id::bigint = cs.user_id::bigint;

-- Note: From now on, match counting will be handled manually in the bot code
-- when updating career_stats after each match completion
