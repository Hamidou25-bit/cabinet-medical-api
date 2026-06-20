ALTER TABLE examens_complementaires
    ADD COLUMN IF NOT EXISTS statut TEXT NOT NULL DEFAULT 'termine';

ALTER TABLE examens_complementaires
    ADD COLUMN IF NOT EXISTS prescripteur_id INTEGER REFERENCES utilisateurs(id);

ALTER TABLE examens_complementaires
    ADD COLUMN IF NOT EXISTS date_resultat TEXT;

ALTER TABLE examens_complementaires
    ADD COLUMN IF NOT EXISTS fait_par_id INTEGER REFERENCES utilisateurs(id);
