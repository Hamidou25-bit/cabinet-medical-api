-- Migration : conversion boîte/unité + catégorisation à 3 valeurs (10 juillet 2026)
-- Backup pris avant exécution : ~/backups/avant_stock_boites_20260710_195628.sql
--
-- Décisions (validées par l'utilisateur) :
--  - On étend la colonne `categorie` existante (Phase 16) à 3 valeurs au lieu
--    d'ajouter une colonne type_article parallèle (éviter le doublon de
--    classification, cf. type_stock annulé en Phase 18).
--  - `Quantite` reste en unités, inchangée. `unites_par_boite` sert uniquement
--    de facteur de conversion au réapprovisionnement et à l'affichage.

BEGIN;

-- 1. Facteur de conversion boîte -> unités (1 = article vendu/compté à l'unité)
ALTER TABLE stock
    ADD COLUMN unites_par_boite INTEGER NOT NULL DEFAULT 1;

-- 2. Répartition des 17 articles 'materiel' existants (état constaté le 10/07/2026)
-- Équipements durables : Plateau medical moyen (73), Chaise Metalique (75),
-- Poubelle 30 L Jaune/Rouge/Noir (78, 79, 80), Chariot a 2 Etagere Local (88)
UPDATE stock SET categorie = 'equipement'
WHERE "idStock" IN (73, 75, 78, 79, 80, 88);

-- Tout le reste du 'materiel' est du consommable : bandelettes (77, 89),
-- boîte de sécurité (76), coton (71), gel hydroalcoolique (86), masques (85),
-- sachets poubelle (74), sparadrap (84), TDR palu (87), TDR boîte (82),
-- test de grossesse (83)
UPDATE stock SET categorie = 'consommable'
WHERE categorie = 'materiel';

-- 3. Garde-fou : plus aucune autre valeur possible
--    (le défaut colonne reste 'medicament', inchangé)
ALTER TABLE stock
    ADD CONSTRAINT stock_categorie_check
    CHECK (categorie IN ('medicament', 'consommable', 'equipement'));

COMMIT;
