-- 2026-07-11 : prix unitaire éditable par ligne d'ordonnance (remplace le montant éditable de 6c1afdd/d08bf72)
--
-- Ajout d'une colonne prix_unitaire sur ligne_ordonnance : snapshot du prix unitaire
-- appliqué à la ligne au moment de la vente (pré-rempli depuis stock.PrixVente,
-- modifiable pour patient/tiers, verrouillé sur PrixAchat en usage interne).
-- La colonne montant est conservée et devient dérivée : montant = prix_unitaire × quantite,
-- toujours recalculée côté serveur (api/ordonnances.py::_resoudre_ligne_ordonnance).
-- Aucune écriture sur stock."PrixVente" depuis ce flux.
--
-- pg_dump pris avant : /home/ubuntu/backups/avant_prix_unitaire_20260711.sql

ALTER TABLE ligne_ordonnance ADD COLUMN IF NOT EXISTS prix_unitaire REAL;

-- Backfill des 246 lignes existantes : prix unitaire dérivé du montant figé
-- (quantite est NOT NULL et toujours >= 1 en base, vérifié le 11/07/2026 —
-- NULLIF par sécurité si une quantité 0 apparaissait entre-temps).
UPDATE ligne_ordonnance
SET prix_unitaire = montant / NULLIF(quantite, 0)
WHERE prix_unitaire IS NULL;
