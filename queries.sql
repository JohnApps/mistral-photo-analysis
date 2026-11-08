-- queris.sql
-- find various tags with and or or
--
-- Photos tagged with 'bird' OR 'pet'
SELECT path, tags
FROM photos
WHERE list_has_any(tags, ['bird', 'pet']);

-- Photos tagged with 'bird' AND 'pet'
SELECT path,tags
FROM photos
WHERE list_has_all(tags, ['bird', 'pet']);

