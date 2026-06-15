-- Suppression de is_interne, remplace par type_beneficiaire (cf.
-- 2026_06_14_type_beneficiaire_stock_id.sql). A executer apres backfill
-- de type_beneficiaire='interne' pour les lignes ou is_interne=1.

ALTER TABLE ordonnance
    DROP COLUMN is_interne;
