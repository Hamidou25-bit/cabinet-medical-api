-- Phase 10 : Support des patients externes dans les examens complémentaires
-- Permet d'enregistrer un examen pour un patient non inscrit dans la base (nom libre).
-- patient_id devient optionnel : soit patient_id (patient enregistré) soit nom_patient_externe.

ALTER TABLE examens_complementaires
    ADD COLUMN IF NOT EXISTS nom_patient_externe VARCHAR(200);

ALTER TABLE examens_complementaires
    ALTER COLUMN patient_id DROP NOT NULL;
