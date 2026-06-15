-- Phase 7 : suppression du champ traitement_apres_diagnostic (consultations)
-- Champ jugé redondant avec le module Ordonnances (gestion des prescriptions/traitements)
ALTER TABLE consultations DROP COLUMN IF EXISTS traitement_apres_diagnostic;
