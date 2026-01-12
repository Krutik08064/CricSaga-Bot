-- ============================================
-- CRICSAGA BOT - COMPLETE DATABASE SETUP
-- ============================================
-- Consolidated SQL setup for CricSaga Cricket Bot
-- Run this script in your Supabase SQL Editor
-- All database tables, indexes, functions, and triggers in one file
-- ============================================
-- Created: January 12, 2026
-- ============================================

-- ============================================
-- SECTION 1: CLEAN SLATE (Optional)
-- ============================================
-- Uncomment below to reset everything
/*
DROP TABLE IF EXISTS achievements CASCADE;
DROP TABLE IF EXISTS team_matches CASCADE;
DROP TABLE IF EXISTS command_logs CASCADE;
DROP TABLE IF EXISTS match_stats CASCADE;
DROP TABLE IF EXISTS player_stats CASCADE;
DROP TABLE IF EXISTS bot_admins CASCADE;
DROP TABLE IF EXISTS authorized_groups CASCADE;
DROP TABLE IF EXISTS scorecards CASCADE;
DROP TABLE IF EXISTS bot_stats CASCADE;
DROP TABLE IF EXISTS schema_version CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS career_stats CASCADE;
DROP TABLE IF EXISTS ranked_matches CASCADE;
DROP TABLE IF EXISTS ranked_queue CASCADE;
DROP TABLE IF EXISTS challenge_cooldowns CASCADE;
DROP TABLE IF EXISTS pending_challenges CASCADE;
DROP TABLE IF EXISTS match_patterns CASCADE;
DROP TABLE IF EXISTS suspicious_activities CASCADE;
DROP TABLE IF EXISTS match_history_detailed CASCADE;
DROP TABLE IF EXISTS game_modes CASCADE;
*/

-- ============================================
-- SECTION 2: CORE TABLES
-- ============================================

-- Table: users (Core table - must be first)
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255) NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_banned BOOLEAN DEFAULT FALSE,
    ban_reason TEXT,
    banned_at TIMESTAMP,
    banned_by BIGINT
);

-- Table: schema_version
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial schema version
INSERT INTO schema_version (version) 
VALUES (2) 
ON CONFLICT (version) DO UPDATE SET version = 2, updated_at = CURRENT_TIMESTAMP;

-- ============================================
-- SECTION 3: GAME DATA TABLES
-- ============================================

-- Table: game_modes
CREATE TABLE IF NOT EXISTS game_modes (
    id SERIAL PRIMARY KEY,
    mode_name VARCHAR(50) UNIQUE NOT NULL,
    max_overs INTEGER,
    max_wickets INTEGER,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default game modes
INSERT INTO game_modes (mode_name, max_overs, max_wickets, description, is_active) 
VALUES 
    ('classic', 10, 10, 'Traditional cricket with limited overs and wickets', TRUE),
    ('quick', 5, 999, 'Fast-paced match with unlimited wickets', TRUE),
    ('survival', 999, 1, 'One wicket challenge - last man standing', TRUE)
ON CONFLICT (mode_name) DO NOTHING;

-- Table: scorecards (Match data storage)
CREATE TABLE IF NOT EXISTS scorecards (
    match_id VARCHAR(50) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    match_name VARCHAR(100),
    game_mode VARCHAR(20) DEFAULT 'classic',
    match_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Table: match_stats
CREATE TABLE IF NOT EXISTS match_stats (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(50) REFERENCES scorecards(match_id) ON DELETE CASCADE,
    total_runs INTEGER DEFAULT 0,
    total_wickets INTEGER DEFAULT 0,
    total_overs DECIMAL(5,1) DEFAULT 0,
    boundaries INTEGER DEFAULT 0,
    sixes INTEGER DEFAULT 0,
    dot_balls INTEGER DEFAULT 0,
    best_over_score INTEGER DEFAULT 0,
    required_run_rate DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: team_matches (For multiplayer teams)
CREATE TABLE IF NOT EXISTS team_matches (
    match_id VARCHAR(50) PRIMARY KEY,
    team1_name VARCHAR(255) NOT NULL,
    team2_name VARCHAR(255) NOT NULL,
    team1_captain BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    team2_captain BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    match_type VARCHAR(50) DEFAULT 'team',
    match_status VARCHAR(20) DEFAULT 'pending',
    match_data JSONB,
    winner_team VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- ============================================
-- SECTION 4: PLAYER STATISTICS
-- ============================================

-- Table: player_stats (Enhanced)
CREATE TABLE IF NOT EXISTS player_stats (
    user_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    matches_played INTEGER DEFAULT 0,
    matches_won INTEGER DEFAULT 0,
    total_runs INTEGER DEFAULT 0,
    total_wickets INTEGER DEFAULT 0,
    total_balls_faced INTEGER DEFAULT 0,
    highest_score INTEGER DEFAULT 0,
    best_bowling VARCHAR(20) DEFAULT '0/0',
    total_fours INTEGER DEFAULT 0,
    total_sixes INTEGER DEFAULT 0,
    fifties INTEGER DEFAULT 0,
    hundreds INTEGER DEFAULT 0,
    five_wicket_hauls INTEGER DEFAULT 0,
    hat_tricks INTEGER DEFAULT 0,
    dot_balls INTEGER DEFAULT 0,
    average DECIMAL(10,2) DEFAULT 0,
    strike_rate DECIMAL(10,2) DEFAULT 0,
    economy_rate DECIMAL(10,2) DEFAULT 0,
    avg_runs_per_match DECIMAL(10,2) DEFAULT 0,
    avg_wickets_per_match DECIMAL(10,2) DEFAULT 0,
    last_five_scores TEXT DEFAULT '[]',
    last_played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Additional columns for bb.py compatibility
    total_runs_scored INTEGER DEFAULT 0,
    total_wickets_taken INTEGER DEFAULT 0,
    total_boundaries INTEGER DEFAULT 0
);

-- Table: achievements
CREATE TABLE IF NOT EXISTS achievements (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    achievement_type VARCHAR(50) NOT NULL,
    achievement_data JSONB,
    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, achievement_type)
);

-- ============================================
-- SECTION 5: CAREER & RANKED SYSTEM
-- ============================================

-- Table: career_stats (Main player career data)
CREATE TABLE IF NOT EXISTS career_stats (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    rating INT DEFAULT 1000,
    rank_tier VARCHAR(50) DEFAULT 'Gold I',
    total_matches INT DEFAULT 0,
    wins INT DEFAULT 0,
    losses INT DEFAULT 0,
    current_streak INT DEFAULT 0,
    streak_type VARCHAR(10) DEFAULT 'none',
    highest_rating INT DEFAULT 1000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Anti-cheat columns
    trust_score INT DEFAULT 50,
    rating_suspended BOOLEAN DEFAULT FALSE,
    suspension_reason TEXT,
    account_flagged BOOLEAN DEFAULT FALSE
);

-- Table: ranked_matches
CREATE TABLE IF NOT EXISTS ranked_matches (
    match_id SERIAL PRIMARY KEY,
    player1_id BIGINT,
    player2_id BIGINT,
    winner_id BIGINT,
    match_type VARCHAR(20) DEFAULT 'ranked',
    
    -- Rating info for player 1
    p1_rating_before INT,
    p1_rating_after INT,
    p1_rating_change INT,
    
    -- Rating info for player 2
    p2_rating_before INT,
    p2_rating_after INT,
    p2_rating_change INT,
    
    -- Match details
    p1_score INT,
    p1_wickets INT,
    p1_overs DECIMAL(4,1),
    
    p2_score INT,
    p2_wickets INT,
    p2_overs DECIMAL(4,1),
    
    performance_bonus INT DEFAULT 0,
    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: ranked_queue (for matchmaking)
CREATE TABLE IF NOT EXISTS ranked_queue (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    rating INTEGER NOT NULL,
    rank_tier TEXT NOT NULL,
    joined_at TIMESTAMP DEFAULT NOW(),
    searching_since TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- SECTION 6: CHALLENGE SYSTEM
-- ============================================

-- Table: challenge_cooldowns (to prevent spam)
CREATE TABLE IF NOT EXISTS challenge_cooldowns (
    id SERIAL PRIMARY KEY,
    challenger_id BIGINT NOT NULL,
    target_id BIGINT NOT NULL,
    challenged_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    UNIQUE(challenger_id, target_id)
);

-- Table: pending_challenges (track active challenges)
CREATE TABLE IF NOT EXISTS pending_challenges (
    id SERIAL PRIMARY KEY,
    challenge_id VARCHAR(20) UNIQUE NOT NULL,
    challenger_id BIGINT NOT NULL,
    target_id BIGINT NOT NULL,
    challenger_name VARCHAR(255),
    target_name VARCHAR(255),
    challenger_rating INT,
    target_rating INT,
    challenger_rank VARCHAR(50),
    target_rank VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
);

-- ============================================
-- SECTION 7: ANTI-CHEAT SYSTEM
-- ============================================

-- Table: match_patterns (Tracks how often two players face each other)
CREATE TABLE IF NOT EXISTS match_patterns (
    player_id VARCHAR(50) NOT NULL,
    opponent_id VARCHAR(50) NOT NULL,
    total_matches INT DEFAULT 0,
    wins INT DEFAULT 0,
    losses INT DEFAULT 0,
    last_match_time TIMESTAMP DEFAULT NOW(),
    matches_last_24h INT DEFAULT 0,
    last_24h_reset TIMESTAMP DEFAULT NOW(),
    is_flagged BOOLEAN DEFAULT FALSE,
    flag_reason TEXT,
    PRIMARY KEY (player_id, opponent_id)
);

-- Table: suspicious_activities (Logs all suspicious activities)
CREATE TABLE IF NOT EXISTS suspicious_activities (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    opponent_id VARCHAR(50),
    details TEXT,
    trust_score_impact INT DEFAULT 0,
    flagged_at TIMESTAMP DEFAULT NOW(),
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(50),
    reviewed_at TIMESTAMP,
    admin_action TEXT,
    cleared BOOLEAN DEFAULT FALSE
);

-- Table: match_history_detailed (Detailed match history)
CREATE TABLE IF NOT EXISTS match_history_detailed (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(100) UNIQUE,
    player1_id VARCHAR(50) NOT NULL,
    player2_id VARCHAR(50) NOT NULL,
    winner_id VARCHAR(50),
    match_type VARCHAR(20),
    rating_change_p1 INT DEFAULT 0,
    rating_change_p2 INT DEFAULT 0,
    match_duration INT,
    total_balls INT,
    match_date TIMESTAMP DEFAULT NOW(),
    flagged BOOLEAN DEFAULT FALSE,
    flag_reason TEXT
);

-- ============================================
-- SECTION 8: ADMINISTRATION
-- ============================================

-- Table: bot_admins
CREATE TABLE IF NOT EXISTS bot_admins (
    admin_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    added_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_super_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Table: authorized_groups
CREATE TABLE IF NOT EXISTS authorized_groups (
    group_id BIGINT PRIMARY KEY,
    group_name VARCHAR(255),
    added_by BIGINT REFERENCES users(telegram_id) ON DELETE SET NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_test_group BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Table: command_logs
CREATE TABLE IF NOT EXISTS command_logs (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
    command VARCHAR(50) NOT NULL,
    chat_type VARCHAR(20),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: bot_stats
CREATE TABLE IF NOT EXISTS bot_stats (
    id SERIAL PRIMARY KEY,
    total_users INTEGER DEFAULT 0,
    total_games_played INTEGER DEFAULT 0,
    active_games INTEGER DEFAULT 0,
    total_commands_used INTEGER DEFAULT 0,
    uptime_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial bot stats
INSERT INTO bot_stats (total_users, total_games_played, active_games, total_commands_used)
VALUES (0, 0, 0, 0)
ON CONFLICT DO NOTHING;

-- ============================================
-- SECTION 9: INDEXES FOR PERFORMANCE
-- ============================================

-- Users indexes
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned);

-- Scorecards indexes
CREATE INDEX IF NOT EXISTS idx_scorecards_user_id ON scorecards(user_id);
CREATE INDEX IF NOT EXISTS idx_scorecards_match_id ON scorecards(match_id);
CREATE INDEX IF NOT EXISTS idx_scorecards_game_mode ON scorecards(game_mode);
CREATE INDEX IF NOT EXISTS idx_scorecards_created_at ON scorecards(created_at DESC);

-- Player stats indexes
CREATE INDEX IF NOT EXISTS idx_player_stats_user_id ON player_stats(user_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_total_runs ON player_stats(total_runs DESC);
CREATE INDEX IF NOT EXISTS idx_player_stats_total_wickets ON player_stats(total_wickets DESC);
CREATE INDEX IF NOT EXISTS idx_player_stats_matches_won ON player_stats(matches_won DESC);
CREATE INDEX IF NOT EXISTS idx_player_stats_highest_score ON player_stats(highest_score DESC);

-- Match stats indexes
CREATE INDEX IF NOT EXISTS idx_match_stats_match_id ON match_stats(match_id);

-- Command logs indexes
CREATE INDEX IF NOT EXISTS idx_command_logs_telegram_id ON command_logs(telegram_id);
CREATE INDEX IF NOT EXISTS idx_command_logs_command ON command_logs(command);
CREATE INDEX IF NOT EXISTS idx_command_logs_created_at ON command_logs(created_at DESC);

-- Achievements indexes
CREATE INDEX IF NOT EXISTS idx_achievements_user_id ON achievements(user_id);
CREATE INDEX IF NOT EXISTS idx_achievements_type ON achievements(achievement_type);

-- Authorized groups indexes
CREATE INDEX IF NOT EXISTS idx_authorized_groups_group_id ON authorized_groups(group_id);
CREATE INDEX IF NOT EXISTS idx_authorized_groups_active ON authorized_groups(is_active);

-- Team matches indexes
CREATE INDEX IF NOT EXISTS idx_team_matches_match_id ON team_matches(match_id);
CREATE INDEX IF NOT EXISTS idx_team_matches_status ON team_matches(match_status);

-- Career stats indexes
CREATE INDEX IF NOT EXISTS idx_career_rating ON career_stats(rating DESC);
CREATE INDEX IF NOT EXISTS idx_career_username ON career_stats(username);
CREATE INDEX IF NOT EXISTS idx_career_trust_score ON career_stats(trust_score);
CREATE INDEX IF NOT EXISTS idx_career_suspended ON career_stats(rating_suspended) WHERE rating_suspended = TRUE;

-- Ranked matches indexes
CREATE INDEX IF NOT EXISTS idx_ranked_player1 ON ranked_matches(player1_id);
CREATE INDEX IF NOT EXISTS idx_ranked_player2 ON ranked_matches(player2_id);
CREATE INDEX IF NOT EXISTS idx_ranked_date ON ranked_matches(match_date DESC);

-- Ranked queue indexes
CREATE INDEX IF NOT EXISTS idx_ranked_queue_rating ON ranked_queue(rating);
CREATE INDEX IF NOT EXISTS idx_ranked_queue_joined ON ranked_queue(joined_at);

-- Challenge system indexes
CREATE INDEX IF NOT EXISTS idx_cooldowns_challenger ON challenge_cooldowns(challenger_id, target_id);
CREATE INDEX IF NOT EXISTS idx_cooldowns_expiry ON challenge_cooldowns(expires_at);
CREATE INDEX IF NOT EXISTS idx_challenges_id ON pending_challenges(challenge_id);
CREATE INDEX IF NOT EXISTS idx_challenges_target ON pending_challenges(target_id);
CREATE INDEX IF NOT EXISTS idx_challenges_status ON pending_challenges(status);
CREATE INDEX IF NOT EXISTS idx_challenges_expiry ON pending_challenges(expires_at);

-- Anti-cheat indexes
CREATE INDEX IF NOT EXISTS idx_match_patterns_player ON match_patterns(player_id);
CREATE INDEX IF NOT EXISTS idx_match_patterns_flagged ON match_patterns(is_flagged) WHERE is_flagged = TRUE;
CREATE INDEX IF NOT EXISTS idx_suspicious_user ON suspicious_activities(user_id);
CREATE INDEX IF NOT EXISTS idx_suspicious_reviewed ON suspicious_activities(reviewed) WHERE reviewed = FALSE;
CREATE INDEX IF NOT EXISTS idx_suspicious_type ON suspicious_activities(activity_type);
CREATE INDEX IF NOT EXISTS idx_match_history_player1 ON match_history_detailed(player1_id);
CREATE INDEX IF NOT EXISTS idx_match_history_player2 ON match_history_detailed(player2_id);
CREATE INDEX IF NOT EXISTS idx_match_history_date ON match_history_detailed(match_date);
CREATE INDEX IF NOT EXISTS idx_match_history_flagged ON match_history_detailed(flagged) WHERE flagged = TRUE;

-- ============================================
-- SECTION 10: DATABASE FUNCTIONS
-- ============================================

-- Function: Update player stats after match
CREATE OR REPLACE FUNCTION update_player_stats_after_match()
RETURNS TRIGGER AS $$
BEGIN
    -- Initialize player_stats if not exists
    INSERT INTO player_stats (user_id, matches_played)
    VALUES (NEW.user_id, 0)
    ON CONFLICT (user_id) DO NOTHING;
    
    -- Update match count
    UPDATE player_stats
    SET 
        matches_played = matches_played + 1,
        last_played_at = NEW.created_at,
        last_updated = CURRENT_TIMESTAMP
    WHERE user_id = NEW.user_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function: Update career timestamp
CREATE OR REPLACE FUNCTION update_career_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function: Update match patterns
CREATE OR REPLACE FUNCTION update_match_patterns()
RETURNS TRIGGER AS $$
BEGIN
    -- Update for player 1
    INSERT INTO match_patterns (player_id, opponent_id, total_matches, wins, losses, last_match_time, matches_last_24h, last_24h_reset)
    VALUES (NEW.player1_id, NEW.player2_id, 1, 
            CASE WHEN NEW.winner_id = NEW.player1_id THEN 1 ELSE 0 END,
            CASE WHEN NEW.winner_id = NEW.player2_id THEN 1 ELSE 0 END,
            NOW(), 1, NOW())
    ON CONFLICT (player_id, opponent_id) 
    DO UPDATE SET
        total_matches = match_patterns.total_matches + 1,
        wins = match_patterns.wins + CASE WHEN NEW.winner_id = NEW.player1_id THEN 1 ELSE 0 END,
        losses = match_patterns.losses + CASE WHEN NEW.winner_id = NEW.player2_id THEN 1 ELSE 0 END,
        last_match_time = NOW(),
        matches_last_24h = CASE 
            WHEN NOW() - match_patterns.last_24h_reset > INTERVAL '24 hours' THEN 1
            ELSE match_patterns.matches_last_24h + 1
        END,
        last_24h_reset = CASE 
            WHEN NOW() - match_patterns.last_24h_reset > INTERVAL '24 hours' THEN NOW()
            ELSE match_patterns.last_24h_reset
        END;
    
    -- Update for player 2
    INSERT INTO match_patterns (player_id, opponent_id, total_matches, wins, losses, last_match_time, matches_last_24h, last_24h_reset)
    VALUES (NEW.player2_id, NEW.player1_id, 1,
            CASE WHEN NEW.winner_id = NEW.player2_id THEN 1 ELSE 0 END,
            CASE WHEN NEW.winner_id = NEW.player1_id THEN 1 ELSE 0 END,
            NOW(), 1, NOW())
    ON CONFLICT (player_id, opponent_id)
    DO UPDATE SET
        total_matches = match_patterns.total_matches + 1,
        wins = match_patterns.wins + CASE WHEN NEW.winner_id = NEW.player2_id THEN 1 ELSE 0 END,
        losses = match_patterns.losses + CASE WHEN NEW.winner_id = NEW.player1_id THEN 1 ELSE 0 END,
        last_match_time = NOW(),
        matches_last_24h = CASE 
            WHEN NOW() - match_patterns.last_24h_reset > INTERVAL '24 hours' THEN 1
            ELSE match_patterns.matches_last_24h + 1
        END,
        last_24h_reset = CASE 
            WHEN NOW() - match_patterns.last_24h_reset > INTERVAL '24 hours' THEN NOW()
            ELSE match_patterns.last_24h_reset
        END;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Function: Cleanup match patterns (run daily)
CREATE OR REPLACE FUNCTION cleanup_match_patterns()
RETURNS void AS $$
BEGIN
    UPDATE match_patterns
    SET matches_last_24h = 0,
        last_24h_reset = NOW()
    WHERE NOW() - last_24h_reset > INTERVAL '24 hours';
END;
$$ LANGUAGE plpgsql;

-- Function: Cleanup expired challenges
CREATE OR REPLACE FUNCTION cleanup_expired_challenges()
RETURNS void AS $$
BEGIN
    -- Delete expired cooldowns
    DELETE FROM challenge_cooldowns WHERE expires_at < NOW();
    
    -- Mark expired challenges as 'expired'
    UPDATE pending_challenges 
    SET status = 'expired' 
    WHERE expires_at < NOW() AND status = 'pending';
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- SECTION 11: TRIGGERS
-- ============================================

-- Trigger: Update player stats after match
DROP TRIGGER IF EXISTS trigger_update_player_stats ON scorecards;
CREATE TRIGGER trigger_update_player_stats
    AFTER INSERT ON scorecards
    FOR EACH ROW
    EXECUTE FUNCTION update_player_stats_after_match();

-- Trigger: Update career timestamp
DROP TRIGGER IF EXISTS update_career_stats_timestamp ON career_stats;
CREATE TRIGGER update_career_stats_timestamp
    BEFORE UPDATE ON career_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_career_timestamp();

-- Trigger: Update match patterns
DROP TRIGGER IF EXISTS trigger_update_match_patterns ON match_history_detailed;
CREATE TRIGGER trigger_update_match_patterns
AFTER INSERT ON match_history_detailed
FOR EACH ROW EXECUTE FUNCTION update_match_patterns();

-- ============================================
-- SECTION 12: VIEWS FOR ANALYTICS
-- ============================================

-- View: Top players
CREATE OR REPLACE VIEW v_top_players AS
SELECT 
    u.telegram_id,
    u.first_name,
    u.username,
    ps.matches_played,
    ps.matches_won,
    ps.total_runs,
    ps.total_wickets,
    ps.highest_score,
    ps.average,
    ps.strike_rate,
    ROUND((ps.matches_won::DECIMAL / NULLIF(ps.matches_played, 0) * 100), 2) as win_percentage
FROM users u
JOIN player_stats ps ON u.telegram_id = ps.user_id
WHERE ps.matches_played > 0
ORDER BY ps.total_runs DESC;

-- View: Recent matches
CREATE OR REPLACE VIEW v_recent_matches AS
SELECT 
    s.match_id,
    s.game_mode,
    u.first_name as player_name,
    s.created_at,
    s.match_data->>'winner' as winner,
    s.match_data->>'score' as score
FROM scorecards s
JOIN users u ON s.user_id = u.telegram_id
ORDER BY s.created_at DESC
LIMIT 50;

-- ============================================
-- SECTION 13: DATA INITIALIZATION
-- ============================================

-- Set default trust scores for existing users
UPDATE career_stats 
SET trust_score = 50 
WHERE trust_score IS NULL;

-- Sync player_stats columns
UPDATE player_stats SET 
    total_runs_scored = total_runs,
    total_wickets_taken = total_wickets,
    total_boundaries = total_fours
WHERE total_runs_scored = 0 OR total_wickets_taken = 0;

-- Update existing admins to be active
UPDATE bot_admins SET is_active = TRUE WHERE is_active IS NULL;

-- ============================================
-- SECTION 14: VERIFICATION QUERIES
-- ============================================

-- Check all tables exist
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Check table row counts
SELECT 
    'users' as table_name, COUNT(*) as row_count FROM users
UNION ALL
SELECT 'scorecards', COUNT(*) FROM scorecards
UNION ALL
SELECT 'player_stats', COUNT(*) FROM player_stats
UNION ALL
SELECT 'career_stats', COUNT(*) FROM career_stats
UNION ALL
SELECT 'bot_admins', COUNT(*) FROM bot_admins
UNION ALL
SELECT 'authorized_groups', COUNT(*) FROM authorized_groups
UNION ALL
SELECT 'game_modes', COUNT(*) FROM game_modes
UNION ALL
SELECT 'ranked_queue', COUNT(*) FROM ranked_queue
UNION ALL
SELECT 'pending_challenges', COUNT(*) FROM pending_challenges
UNION ALL
SELECT 'match_patterns', COUNT(*) FROM match_patterns
UNION ALL
SELECT 'schema_version', COUNT(*) FROM schema_version;

-- ============================================
-- SETUP COMPLETE! 🎉
-- ============================================
-- All database tables, indexes, functions, and triggers have been created
-- Your CricSaga Bot database is now ready!
-- 
-- Next steps:
-- 1. Update your .env file with Supabase credentials
-- 2. Run: python bb.py
-- 
-- For maintenance, you can run these periodic cleanup functions:
-- - SELECT cleanup_match_patterns();
-- - SELECT cleanup_expired_challenges();
-- ============================================
