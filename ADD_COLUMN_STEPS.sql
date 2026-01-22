-- Step 1: Check if column already exists
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'career_stats' 
  AND column_name = 'total_ranked_matches';

-- If the above returns nothing, try adding column in steps:

-- Step 2: Add column WITHOUT default (much faster)
ALTER TABLE career_stats ADD COLUMN IF NOT EXISTS total_ranked_matches INT;

-- Step 3: Set values for existing rows
UPDATE career_stats SET total_ranked_matches = 0 WHERE total_ranked_matches IS NULL;

-- Step 4: Set default for future rows
ALTER TABLE career_stats ALTER COLUMN total_ranked_matches SET DEFAULT 0;

-- Step 5: Verify
SELECT user_id, rating, total_ranked_matches FROM career_stats LIMIT 5;
