-- Phase 27 — lien entre un compte utilisateur (rôle medecin) et une ligne medecin,
-- nécessaire pour le self-service du Bilan de garde (medecin_id du JWT ne pointait
-- jusqu'ici vers aucune table : utilisateurs et medecin sont des espaces d'ID séparés).
ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS medecin_id INTEGER REFERENCES medecin(id);
