-- Migration : suivi d'état des équipements (12 juillet 2026)
-- Préalable : pg_dump pris avant exécution (~/backups/avant_statut_equipement_20260712_142146.sql)
--
-- Nouvelle colonne stock.statut_equipement, pertinente uniquement pour
-- categorie = 'equipement' : NULL pour toutes les autres catégories (pas de
-- DEFAULT colonne, sinon les insertions de médicaments/consommables porteraient
-- un statut sans signification). Le défaut fonctionnel 'bon_etat' est posé par
-- le code (stock.py / achats.py) à la création d'un article équipement.

BEGIN;

ALTER TABLE stock ADD COLUMN statut_equipement VARCHAR(20)
    CHECK (statut_equipement IN ('bon_etat', 'en_utilisation', 'a_remplacer'));

-- Backfill : les équipements existants démarrent en 'bon_etat'
UPDATE stock SET statut_equipement = 'bon_etat' WHERE categorie = 'equipement';

COMMIT;

-- Note : la date d'achat d'un équipement n'a PAS nécessité de nouvelle colonne —
-- stock."DateEntree" est déjà alimentée par la date_achat de l'achat qui crée
-- l'article (achats.py::_creer_article_stock_pour_ligne) et sert de date d'achat
-- affichée sur l'onglet Équipement.
