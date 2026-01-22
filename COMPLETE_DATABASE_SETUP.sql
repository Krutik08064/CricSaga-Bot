-- ================================================
-- CRICSAGA BOT - COMPLETE DATABASE SETUP
-- ================================================
-- This file contains all table creations, alterations, and indexes
-- Run this once to set up the entire database from scratch
-- Or run sections individually as needed
-- ================================================

-- ================================================
-- SECTION 1: CAREER STATS TABLE (Ranking/Rating System)
-- ================================================
CREATE TABLE IF NOT EXISTS career_stats (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255) DEFAULT '',
    rating INT DEFAULT 1000,
    rank_tier VARCHAR(50) DEFAULT 'Gold I',
    total_matches INT DEFAULT 0,
    wins INT DEFAULT 0,
    losses INT DEFAULT 0,
    current_streak INT DEFAULT 0,
    streak_type VARCHAR(10) DEFAULT 'none',
    highest_rating INT DEFAULT 1000,
    trust_score FLOAT DEFAULT 100.0,
    rating_suspended BOOLEAN DEFAULT FALSE,
    suspension_reason TEXT DEFAULT '',
    account_flagged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add total_ranked_matches column for placement match tracking
ALTER TABLE career_stats ADD COLUMN IF NOT EXISTS total_ranked_matches INT DEFAULT 0;

-- Indexes for career_stats
CREATE INDEX IF NOT EXISTS idx_career_rating ON career_stats(rating DESC);
CREATE INDEX IF NOT EXISTS idx_career_rank ON career_stats(rank_tier);
CREATE INDEX IF NOT EXISTS idx_career_ranked_matches ON career_stats(total_ranked_matches);

-- ================================================
-- SECTION 2: PLAYER STATS TABLE (Profile/Performance Stats)
-- ================================================
CREATE TABLE IF NOT EXISTS player_stats (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255) DEFAULT '',
    matches_played INT DEFAULT 0,
    matches_won INT DEFAULT 0,
    total_runs_scored INT DEFAULT 0,
    total_wickets_taken INT DEFAULT 0,
    total_balls_faced INT DEFAULT 0,
    highest_score INT DEFAULT 0,
    total_boundaries INT DEFAULT 0,
    total_sixes INT DEFAULT 0,
    dot_balls INT DEFAULT 0,
    fifties INT DEFAULT 0,
    hundreds INT DEFAULT 0,
    best_bowling VARCHAR(20) DEFAULT '',
    last_five_scores TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for player_stats
CREATE INDEX IF NOT EXISTS idx_player_matches ON player_stats(matches_played DESC);
CREATE INDEX IF NOT EXISTS idx_player_runs ON player_stats(total_runs_scored DESC);

-- ================================================
-- SECTION 3: RANKED MATCHES TABLE (Match History)
-- ================================================
CREATE TABLE IF NOT EXISTS ranked_matches (
    id SERIAL PRIMARY KEY,
    player1_id BIGINT NOT NULL,
    player2_id BIGINT NOT NULL,
    winner_id BIGINT,
    p1_rating_before INT NOT NULL,
    p1_rating_after INT NOT NULL,
    p1_rating_change INT NOT NULL,
    p2_rating_before INT NOT NULL,
    p2_rating_after INT NOT NULL,
    p2_rating_change INT NOT NULL,
    p1_score INT DEFAULT 0,
    p1_wickets INT DEFAULT 0,
    p1_overs FLOAT DEFAULT 0,
    p2_score INT DEFAULT 0,
    p2_wickets INT DEFAULT 0,
    p2_overs FLOAT DEFAULT 0,
    match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for ranked_matches
CREATE INDEX IF NOT EXISTS idx_ranked_matches_players ON ranked_matches(player1_id, player2_id);
CREATE INDEX IF NOT EXISTS idx_ranked_matches_winner ON ranked_matches(winner_id);
CREATE INDEX IF NOT EXISTS idx_ranked_matches_date ON ranked_matches(match_date DESC);

-- ================================================
-- SECTION 4: ANTI-CHEAT SYSTEM TABLES
-- ================================================

-- Suspicious activity tracking
CREATE TABLE IF NOT EXISTS suspicious_activities (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    opponent_id BIGINT,
    reason TEXT,
    trust_penalty FLOAT DEFAULT 0,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_suspicious_user ON suspicious_activities(user_id);
CREATE INDEX IF NOT EXISTS idx_suspicious_type ON suspicious_activities(activity_type);

-- Detailed match history for pattern analysis
CREATE TABLE IF NOT EXISTS match_history_detailed (
    id SERIAL PRIMARY KEY,
    match_id BIGINT,
    player1_id BIGINT NOT NULL,
    player2_id BIGINT NOT NULL,
    winner_id BIGINT,
    match_type VARCHAR(20) DEFAULT 'ranked',
    player1_score INT DEFAULT 0,
    player2_score INT DEFAULT 0,
    p1_rating_change INT DEFAULT 0,
    p2_rating_change INT DEFAULT 0,
    match_duration_seconds INT DEFAULT 0,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_match_history_p1 ON match_history_detailed(player1_id);
CREATE INDEX IF NOT EXISTS idx_match_history_p2 ON match_history_detailed(player2_id);
CREATE INDEX IF NOT EXISTS idx_match_history_date ON match_history_detailed(played_at DESC);

-- ================================================
-- SECTION 5: USER MANAGEMENT TABLES
-- ================================================

-- Users table (for all users)
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_banned BOOLEAN DEFAULT FALSE
);

-- Registered users (for subscription/membership tracking)
CREATE TABLE IF NOT EXISTS registered_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Blacklisted users
CREATE TABLE IF NOT EXISTS blacklisted_users (
    user_id BIGINT PRIMARY KEY,
    reason TEXT,
    blacklisted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bot admins
CREATE TABLE IF NOT EXISTS bot_admins (
    admin_id BIGINT PRIMARY KEY,
    added_by BIGINT,
    is_super_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Admin users (legacy - keeping for compatibility)
CREATE TABLE IF NOT EXISTS admin_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Authorized groups
CREATE TABLE IF NOT EXISTS authorized_groups (
    group_id BIGINT PRIMARY KEY,
    group_name VARCHAR(255),
    added_by BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ================================================
-- SECTION 6: GAME & MATCH TABLES
-- ================================================

-- Scorecards for saved matches
CREATE TABLE IF NOT EXISTS scorecards (
    match_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    match_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Ranked queue for matchmaking
CREATE TABLE IF NOT EXISTS ranked_queue (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    rating INT DEFAULT 1000,
    rank_tier VARCHAR(50) DEFAULT 'Gold I',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pending challenges
CREATE TABLE IF NOT EXISTS pending_challenges (
    challenge_id SERIAL PRIMARY KEY,
    challenger_id BIGINT NOT NULL,
    target_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- Challenge cooldowns
CREATE TABLE IF NOT EXISTS challenge_cooldowns (
    id SERIAL PRIMARY KEY,
    challenger_id BIGINT NOT NULL,
    target_id BIGINT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Command logs
CREATE TABLE IF NOT EXISTS command_logs (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    command VARCHAR(100) NOT NULL,
    chat_id BIGINT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for game tables
CREATE INDEX IF NOT EXISTS idx_scorecards_user ON scorecards(user_id);
CREATE INDEX IF NOT EXISTS idx_ranked_queue_rating ON ranked_queue(rating DESC);
CREATE INDEX IF NOT EXISTS idx_pending_challenges_status ON pending_challenges(status);
CREATE INDEX IF NOT EXISTS idx_challenge_cooldowns_expires ON challenge_cooldowns(expires_at);

-- ================================================
-- SECTION 7: VERIFICATION & COMPLETION
-- ================================================

-- ================================================
-- SECTION 7: VERIFICATION & COMPLETION
-- ================================================

-- Verify all tables exist
SELECT 
    'users' as table_name,
    COUNT(*) as row_count
FROM users
UNION ALL
SELECT 'career_stats', COUNT(*) FROM career_stats
UNION ALL
SELECT 'player_stats', COUNT(*) FROM player_stats
UNION ALL
SELECT 'ranked_matches', COUNT(*) FROM ranked_matches
UNION ALL
SELECT 'suspicious_activities', COUNT(*) FROM suspicious_activities
UNION ALL
SELECT 'match_history_detailed', COUNT(*) FROM match_history_detailed
UNION ALL
SELECT 'registered_users', COUNT(*) FROM registered_users
UNION ALL
SELECT 'blacklisted_users', COUNT(*) FROM blacklisted_users
UNION ALL
SELECT 'bot_admins', COUNT(*) FROM bot_admins
UNION ALL
SELECT 'admin_users', COUNT(*) FROM admin_users
UNION ALL
SELECT 'authorized_groups', COUNT(*) FROM authorized_groups
UNION ALL
SELECT 'scorecards', COUNT(*) FROM scorecards
UNION ALL
SELECT 'ranked_queue', COUNT(*) FROM ranked_queue
UNION ALL
SELECT 'pending_challenges', COUNT(*) FROM pending_challenges
UNION ALL
SELECT 'challenge_cooldowns', COUNT(*) FROM challenge_cooldowns
UNION ALL
SELECT 'command_logs', COUNT(*) FROM command_logs
UNION ALL
SELECT 'schema_version', COUNT(*) FROM schema_version;

-- ================================================
-- END OF SETUP
-- ================================================
