-- Phase : numéro de dossier patient automatique + suppression du champ email
-- 1. Backfill des patients sans numero_dossier (NULL ou vide), dans l'ordre de date_enregistrement,
--    en poursuivant la séquence PAT-2026-NNNN déjà utilisée par les 41 autres patients.
-- 2. Contrainte UNIQUE sur numero_dossier (aucun doublon constaté avant migration).
-- 3. Suppression de la colonne email (0 patient sur 48 ne l'utilisait).

WITH a_numeroter AS (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY date_enregistrement, id) AS rang
    FROM patients
    WHERE numero_dossier IS NULL OR numero_dossier = ''
),
dernier AS (
    SELECT COALESCE(MAX(CAST(SUBSTRING(numero_dossier FROM 'PAT-2026-(\d+)') AS INTEGER)), 0) AS max_num
    FROM patients
    WHERE numero_dossier ~ '^PAT-2026-\d+$'
)
UPDATE patients
SET numero_dossier = 'PAT-2026-' || LPAD((dernier.max_num + a_numeroter.rang)::text, 4, '0')
FROM a_numeroter, dernier
WHERE patients.id = a_numeroter.id;

ALTER TABLE patients
    ADD CONSTRAINT patients_numero_dossier_unique UNIQUE (numero_dossier);

ALTER TABLE patients
    DROP COLUMN email;
