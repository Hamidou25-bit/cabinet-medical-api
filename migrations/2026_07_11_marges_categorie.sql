-- Migration : marges par catégorie de stock (Phase marges — 11 juillet 2026)
-- Préalable : pg_dump pris avant exécution (~/backups/avant_marges_categorie_20260711_131845.sql)
--
-- Note : pas de FK REFERENCES stock(categorie) possible (categorie n'est ni PK
-- ni UNIQUE dans stock) — on réplique la contrainte CHECK de stock_categorie_check.

BEGIN;

-- 1. Table des marges par catégorie
CREATE TABLE marges_categorie (
    categorie VARCHAR(20) PRIMARY KEY
        CHECK (categorie IN ('medicament', 'consommable', 'equipement')),
    marge_pourcentage NUMERIC(5,2) NOT NULL DEFAULT 30.00
);

INSERT INTO marges_categorie (categorie, marge_pourcentage) VALUES
    ('medicament', 30.00),
    ('consommable', 30.00),
    ('equipement', 30.00);

-- 2. Marge personnalisée par article (NULL = utiliser la marge de la catégorie)
ALTER TABLE stock ADD COLUMN marge_personnalisee NUMERIC(5,2) NULL;

-- 3. Droits pour l'utilisateur applicatif (la table est créée par postgres ;
--    pas de séquence ici, categorie est une PK texte)
GRANT SELECT, INSERT, UPDATE, DELETE ON marges_categorie TO cabinet_user;

COMMIT;
