-- Migration : lien consommable laboratoire → type d'examen (13 juillet 2026)
-- Préalable : pg_dump pris avant exécution (~/backups/avant_lien_examen_consommable_20260713_171805.sql)
--
-- Deux nouvelles colonnes sur stock, pertinentes uniquement pour
-- categorie = 'consommable_laboratoire' (NULL / défaut pour les autres, la
-- règle est appliquée par le code stock.py, même pattern que statut_equipement) :
--   - sous_type_examen_id : type d'examen (sous_type_examen.id) auquel l'article
--     est associé — pas de FK dure, même convention que le reste du schéma
--     (examens_complementaires.sous_type_examen_id, etc.). La suppression d'un
--     sous_type_examen référencé est bloquée au niveau API (409, examens_types.py).
--   - quantite_examen : quantité consommée par défaut quand un examen de ce type
--     est réalisé (pré-remplissage de la section "Consommables laboratoire
--     utilisés" du modal Examen). REAL NOT NULL DEFAULT 1.

BEGIN;

ALTER TABLE stock ADD COLUMN sous_type_examen_id INTEGER;
ALTER TABLE stock ADD COLUMN quantite_examen REAL NOT NULL DEFAULT 1;

COMMIT;
