-- Ajoute le champ Prescripteur (medecin_id) sur les ordonnances, permettant
-- de tracer qui a prescrit, comme c'est deja le cas pour les consultations.
ALTER TABLE ordonnance ADD COLUMN medecin_id INTEGER;
