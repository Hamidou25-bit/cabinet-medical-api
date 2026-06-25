ALTER TABLE consultations ADD COLUMN IF NOT EXISTS paye BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE soins ADD COLUMN IF NOT EXISTS paye BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE examens_complementaires ADD COLUMN IF NOT EXISTS paye BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ordonnance ADD COLUMN IF NOT EXISTS paye BOOLEAN NOT NULL DEFAULT false;

-- Backfill : les enregistrements déjà existants avant l'introduction de la caisse sont
-- considérés comme déjà encaissés (sinon les recettes des mois passés tomberaient à 0
-- dans la synthèse comptable, qui va désormais filtrer sur paye = true). Seuls les
-- nouveaux enregistrements créés après cette migration nécessiteront un encaissement explicite.
UPDATE consultations SET paye = true;
UPDATE soins SET paye = true;
UPDATE examens_complementaires SET paye = true;
UPDATE ordonnance SET paye = true;
