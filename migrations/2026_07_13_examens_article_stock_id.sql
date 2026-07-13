-- 13/07/2026 — Examens Laboratoire : l'article du Services Laboratoire (stock,
-- categorie='consommable_laboratoire') devient directement le "type" d'examen.
--
--   - article_stock_id : référence stock."idStock" (pas de FK déclarée, même
--     convention que sous_type_examen_id). Renseigné pour les nouveaux examens
--     Laboratoire ; NULL pour l'Imagerie (toujours via sous_type_examen) et les
--     anciens examens Laboratoire (qui gardent leur sous_type_examen_id).
--   - sous_type_examen_id passe nullable : un nouvel examen Laboratoire n'en a plus.
--     Les 13 examens Laboratoire existants conservent le leur (affichage via
--     COALESCE(sous_type_examen.nom, stock."Designation") côté API).
--
-- pg_dump pris avant : ~/backups/avant_examens_article_stock_20260713_183620.sql

ALTER TABLE examens_complementaires ADD COLUMN article_stock_id INTEGER;
ALTER TABLE examens_complementaires ALTER COLUMN sous_type_examen_id DROP NOT NULL;
