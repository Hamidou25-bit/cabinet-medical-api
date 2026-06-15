-- ligne_ordonnance.patient_id doit etre optionnel, comme ordonnance.patient_id,
-- pour les ordonnances de type 'tiers' ou 'interne' (sans patient enregistre).

ALTER TABLE ligne_ordonnance
    ALTER COLUMN patient_id DROP NOT NULL;
