-- Lien de traçabilité entre un soin et l'ordonnance depuis laquelle il a été saisi
-- (nullable : un soin créé depuis le module Soins dédié, ou dont l'ordonnance
-- d'origine a été supprimée, garde une valeur NULL)
ALTER TABLE soins ADD COLUMN IF NOT EXISTS ordonnance_id INTEGER REFERENCES ordonnance(id) ON DELETE SET NULL;
