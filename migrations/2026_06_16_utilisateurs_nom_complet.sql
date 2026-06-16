-- Ajout de la colonne nom_complet à la table utilisateurs
-- pour la gestion des comptes utilisateurs indépendamment du module personnel
ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS nom_complet VARCHAR(200);
