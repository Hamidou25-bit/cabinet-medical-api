-- 2026-07-11 : personne ayant realise le soin (meme principe que ordonnance.medecin_id).
-- Colonne nullable, sans FK declaree (meme convention que consultations.medecin_id et
-- ordonnance.medecin_id, qui referencent medecin(id) sans contrainte).
-- pg_dump pris avant : ~/backups/avant_soins_medecin_20260711.sql

ALTER TABLE soins ADD COLUMN IF NOT EXISTS medecin_id INTEGER;
