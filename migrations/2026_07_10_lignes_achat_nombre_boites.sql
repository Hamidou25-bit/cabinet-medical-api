-- Phase 2.5-B (10/07/2026) : saisie des lignes d'achat en boîtes
--
-- lignes_achat.quantite reste la valeur canonique en UNITÉS (montant,
-- mouvements de stock et annulation _retirer_lignes_du_stock inchangés).
-- nombre_boites est purement informatif (affichage / réédition du formulaire) :
-- renseigné uniquement quand la ligne a été saisie en boîtes, NULL sinon
-- (toutes les lignes historiques restent NULL — saisies en unités).
--
-- ⚠️ pg_dump obligatoire AVANT exécution.

ALTER TABLE lignes_achat
    ADD COLUMN nombre_boites INTEGER NULL;
