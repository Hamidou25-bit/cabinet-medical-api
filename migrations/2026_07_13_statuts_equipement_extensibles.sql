-- Migration : statuts d'équipement extensibles (13 juillet 2026)
--
-- Les 3 statuts de base (bon_etat / en_utilisation / a_remplacer) restent codés
-- en dur (stock_utils.STATUTS_EQUIPEMENT + libellés frontend). L'admin peut
-- désormais ajouter des statuts supplémentaires : libellés libres stockés dans
-- parametres_cabinet ('statuts_equipement_personnalises', séparés par |) et
-- enregistrés tels quels dans stock.statut_equipement.
--
-- La contrainte CHECK posée par 2026_07_12_stock_statut_equipement.sql doit donc
-- être retirée (elle n'accepterait jamais un statut personnalisé) — la validation
-- reste assurée côté API (stock_utils.valider_statut_equipement, avec cursor).

BEGIN;

ALTER TABLE stock DROP CONSTRAINT IF EXISTS stock_statut_equipement_check;

-- VARCHAR(20) était calibré pour les 3 codes de base : élargi pour des libellés libres
ALTER TABLE stock ALTER COLUMN statut_equipement TYPE VARCHAR(50);

INSERT INTO parametres_cabinet (cle, valeur, description) VALUES
('statuts_equipement_personnalises', '', 'Statuts d''équipement supplémentaires (libellés séparés par |), en plus de : Bon état / En cours d''utilisation / À remplacer')
ON CONFLICT (cle) DO NOTHING;

COMMIT;
