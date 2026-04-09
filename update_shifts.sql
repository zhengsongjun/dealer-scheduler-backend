-- 1. Update dealers preferred_shift: day 40%, swing 40%, night 20%
WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (ORDER BY id) AS rn,
         COUNT(*) OVER () AS total
  FROM dealers
)
UPDATE dealers
SET preferred_shift = CASE
  WHEN ranked.rn <= ranked.total * 0.4 THEN 'day'
  WHEN ranked.rn <= ranked.total * 0.8 THEN 'swing'
  ELSE 'night'
END
FROM ranked
WHERE dealers.id = ranked.id;

-- 2. Update availability_requests shift for week_start >= 2026-06-12: day 40%, swing 40%, night 20%
WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (ORDER BY id) AS rn,
         COUNT(*) OVER () AS total
  FROM availability_requests
  WHERE week_start >= '2026-06-12'
)
UPDATE availability_requests
SET shift = CASE
  WHEN ranked.rn <= ranked.total * 0.4 THEN 'day'
  WHEN ranked.rn <= ranked.total * 0.8 THEN 'swing'
  ELSE 'night'
END
FROM ranked
WHERE availability_requests.id = ranked.id;
