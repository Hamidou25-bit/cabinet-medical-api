-- Phase : séparation Médicaments / Matériel médical dans le stock
-- La colonne "Type" existante est un champ texte libre, mal renseigné (59 'Medicament',
-- 19 vides, 1 'Materiel Médical') et non fiable pour un filtrage automatique.
-- Ajout d'une colonne categorie contrôlée ('medicament' | 'materiel').
-- Backfill : tout par défaut en 'medicament' (comportement actuel inchangé dans
-- l'autocomplete des ordonnances), sauf les articles déjà explicitement tagués
-- "Materiel Médical" dans la colonne Type historique.

ALTER TABLE stock
    ADD COLUMN IF NOT EXISTS categorie VARCHAR(20) NOT NULL DEFAULT 'medicament';

UPDATE stock
SET categorie = 'materiel'
WHERE "Type" = 'Materiel Médical';
