-- Phase 9 : Création table type_soin + adaptation table soins
-- À appliquer sur le serveur de production avant de déployer l'API

-- 1. Table des types de soins (nouveau)
CREATE TABLE IF NOT EXISTS type_soin (
    id SERIAL PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    prix_defaut NUMERIC(10,2) NOT NULL DEFAULT 0
);

-- 2. Adaptation de la table soins existante
--    On ajoute les colonnes manquantes (IF NOT EXISTS protège contre les doublons)
ALTER TABLE soins ADD COLUMN IF NOT EXISTS type_soin_id INTEGER REFERENCES type_soin(id);
ALTER TABLE soins ADD COLUMN IF NOT EXISTS patient_id INTEGER REFERENCES patients(id);
ALTER TABLE soins ADD COLUMN IF NOT EXISTS nom_patient_externe VARCHAR(200);
ALTER TABLE soins ADD COLUMN IF NOT EXISTS prix_applique NUMERIC(10,2) NOT NULL DEFAULT 0;
ALTER TABLE soins ADD COLUMN IF NOT EXISTS date_soin DATE;
ALTER TABLE soins ADD COLUMN IF NOT EXISTS notes TEXT;

-- Si patient_id existait déjà dans la table originale (SQLite migration) avec une contrainte NOT NULL,
-- ADD COLUMN IF NOT EXISTS est silencieusement ignoré et la contrainte reste.
-- On la retire explicitement pour permettre les soins de patients externes (patient_id = NULL).
ALTER TABLE soins ALTER COLUMN patient_id DROP NOT NULL;

-- 3. Types de soins par défaut
INSERT INTO type_soin (nom, prix_defaut) VALUES
    ('Injection', 1000),
    ('Pansement', 1500),
    ('Perfusion', 3000),
    ('Nébulisation', 2000),
    ('Suture', 5000),
    ('Sondage', 2500),
    ('Autre soin', 1000)
ON CONFLICT DO NOTHING;
