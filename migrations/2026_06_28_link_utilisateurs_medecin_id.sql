-- Phase 27 (suite) — backfill du lien utilisateurs.medecin_id (colonne ajoutée par
-- 2026_06_28_utilisateurs_medecin_id.sql) pour les 3 comptes de rôle 'medecin'.
-- Sans ce lien, le self-service du Bilan de garde (GET /repartition/bilan-garde)
-- renvoyait 400 "Votre compte n'est lié à aucun médecin" pour ces comptes.
-- Mapping confirmé manuellement par l'utilisateur (pas de correspondance automatique
-- fiable, notamment Dama/Adama) :
--   utilisateurs.id=4 (Bouya)  -> medecin.id=5 (Bouya Coulibaly)
--   utilisateurs.id=5 (Hawa)   -> medecin.id=7 (Hawa Coulibaly)
--   utilisateurs.id=6 (Dama)   -> medecin.id=6 (Adama Coulibaly)
-- pg_dump pris avant (~/backups/avant_link_medecin_id_20260628_201650.sql).

UPDATE utilisateurs SET medecin_id = 5 WHERE id = 4 AND nom_utilisateur = 'Bouya';
UPDATE utilisateurs SET medecin_id = 7 WHERE id = 5 AND nom_utilisateur = 'Hawa';
UPDATE utilisateurs SET medecin_id = 6 WHERE id = 6 AND nom_utilisateur = 'Dama';
