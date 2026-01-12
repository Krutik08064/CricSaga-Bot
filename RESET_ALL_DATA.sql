-- ============================================
-- CRICSAGA BOT - RESET ALL DATA
-- ============================================
-- WARNING: This will DELETE ALL user data!
-- Run this only if you want to start fresh
-- Database structure remains intact
-- ============================================

-- Disable triggers temporarily to avoid cascade issues
SET session_replication_role = 'replica';

-- ============================================
-- CLEAR ALL USER DATA
-- ============================================

-- Clear match and game data
TRUNCATE TABLE scorecards CASCADE;
TRUNCATE TABLE match_stats CASCADE;
TRUNCATE TABLE team_matches CASCADE;
TRUNCATE TABLE match_history_detailed CASCADE;
TRUNCATE TABLE ranked_matches CASCADE;

-- Clear player statistics
TRUNCATE TABLE player_stats CASCADE;
TRUNCATE TABLE career_stats CASCADE;
TRUNCATE TABLE achievements CASCADE;

-- Clear matchmaking and challenges
TRUNCATE TABLE ranked_queue CASCADE;
TRUNCATE TABLE pending_challenges CASCADE;
TRUNCATE TABLE challenge_cooldowns CASCADE;

-- Clear anti-cheat data
TRUNCATE TABLE match_patterns CASCADE;
TRUNCATE TABLE suspicious_activities CASCADE;

-- Clear command logs
TRUNCATE TABLE command_logs CASCADE;

-- Clear users (this will cascade to related tables due to foreign keys)
TRUNCATE TABLE users CASCADE;

-- Reset bot stats
UPDATE bot_stats SET 
    total_users = 0,
    total_games_played = 0,
    active_games = 0,
    total_commands_used = 0,
    uptime_start = CURRENT_TIMESTAMP,
    last_updated = CURRENT_TIMESTAMP;

-- Reset sequences for auto-increment IDs
ALTER SEQUENCE IF EXISTS match_stats_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS ranked_matches_match_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS achievements_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS command_logs_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS suspicious_activities_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS match_history_detailed_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS challenge_cooldowns_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS pending_challenges_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS bot_stats_id_seq RESTART WITH 1;

-- Re-enable triggers
SET session_replication_role = 'origin';

-- ============================================
-- VERIFICATION
-- ============================================
SELECT 
    'users' as table_name, COUNT(*) as remaining_rows FROM users
UNION ALL
SELECT 'scorecards', COUNT(*) FROM scorecards
UNION ALL
SELECT 'player_stats', COUNT(*) FROM player_stats
UNION ALL
SELECT 'career_stats', COUNT(*) FROM career_stats
UNION ALL
SELECT 'ranked_matches', COUNT(*) FROM ranked_matches
UNION ALL
SELECT 'match_history_detailed', COUNT(*) FROM match_history_detailed
UNION ALL
SELECT 'achievements', COUNT(*) FROM achievements
UNION ALL
SELECT 'command_logs', COUNT(*) FROM command_logs
UNION ALL
SELECT 'ranked_queue', COUNT(*) FROM ranked_queue
UNION ALL
SELECT 'pending_challenges', COUNT(*) FROM pending_challenges;

-- ============================================
-- RESET COMPLETE! ✅
-- ============================================
-- All user data has been cleared
-- Database is ready for fresh start
-- ============================================
