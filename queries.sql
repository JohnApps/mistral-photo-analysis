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

-- caption lookup
select full_path from photos where caption ilike '%a woman%';

-- do some fancy searching
--
-- SET scalar_subquery_error_on_multiple_rows=false;
--
-- find photos similar to a known one, then eyeball the paths
--
--
select full_path, caption,
       array_cosine_similarity(embedding,
         (select embedding from photos
          where filename ilike '%JDA9525%' limit 1)) as score
from photos
where embedding is not null
order by score desc limit 30;