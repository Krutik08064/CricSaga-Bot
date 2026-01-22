-- MINIMAL MIGRATION - Just add the column
-- The bot will auto-populate values as users play matches

ALTER TABLE career_stats 
ADD COLUMN IF NOT EXISTS total_ranked_matches INT DEFAULT 0;
