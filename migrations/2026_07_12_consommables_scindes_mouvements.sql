-- Migration : scission de la catégorie 'consommable' en 'consommable_laboratoire'
-- et 'consommable_medical' + table de traçabilité des sorties internes (12 juillet 2026)
-- Préalable : pg_dump pris avant exécution (~/backups/avant_consommables_scindes_20260712_125014.sql)
--
-- ⚠️ La valeur 'consommable' reste TRANSITOIREMENT acceptée par les contraintes CHECK
-- de stock : l'ancien code encore déployé (select frontend + CATEGORIES_VALIDES) écrit
-- toujours cette valeur. À retirer par une migration ultérieure une fois le nouveau
-- code déployé. Aucune ligne ne porte plus cette valeur après cette migration.

BEGIN;

-- 0. Élargir les colonnes categorie : VARCHAR(20) à l'origine, or
--    'consommable_laboratoire' fait 23 caractères.
ALTER TABLE stock ALTER COLUMN categorie TYPE VARCHAR(30);
ALTER TABLE marges_categorie ALTER COLUMN categorie TYPE VARCHAR(30);

-- 1. stock : étendre la contrainte de catégorie puis basculer les articles existants.
--    Choix par défaut : tous les anciens 'consommable' → 'consommable_medical'
--    (reclassement manuel ensuite via l'interface, cf. rapport d'inspection —
--    bandelettes/TDR/tests de grossesse à repasser en 'consommable_laboratoire').
ALTER TABLE stock DROP CONSTRAINT stock_categorie_check;
ALTER TABLE stock ADD CONSTRAINT stock_categorie_check
    CHECK (categorie IN ('medicament', 'consommable', 'consommable_laboratoire',
                         'consommable_medical', 'equipement'));

UPDATE stock SET categorie = 'consommable_medical' WHERE categorie = 'consommable';

-- 2. marges_categorie : suivre la scission (sinon le recalcul des prix, qui fait un
--    JOIN sur cette table, perdrait silencieusement les articles des nouvelles
--    catégories). La nouvelle catégorie labo hérite de la marge de l'ancien
--    'consommable' (30 % au moment de la migration).
ALTER TABLE marges_categorie DROP CONSTRAINT marges_categorie_categorie_check;

UPDATE marges_categorie SET categorie = 'consommable_medical' WHERE categorie = 'consommable';

INSERT INTO marges_categorie (categorie, marge_pourcentage)
SELECT 'consommable_laboratoire', marge_pourcentage
FROM marges_categorie WHERE categorie = 'consommable_medical';

ALTER TABLE marges_categorie ADD CONSTRAINT marges_categorie_categorie_check
    CHECK (categorie IN ('medicament', 'consommable_laboratoire',
                         'consommable_medical', 'equipement'));

-- 3. Table de traçabilité des sorties de consommables (usage non facturé au patient).
--    Distincte de la table historique 'sortie' (231 lignes, liée aux ordonnances).
--    designation = snapshot texte, préservé si l'article de stock est supprimé
--    (stock_id passe alors à NULL, même convention que ligne_ordonnance_stock_id_fkey).
--    examen_id/utilisateur_id en ON DELETE SET NULL : la suppression d'un examen ou
--    d'un utilisateur ne doit pas casser l'historique des mouvements (ni être bloquée).
CREATE TABLE mouvements_consommable (
    id SERIAL PRIMARY KEY,
    stock_id INTEGER REFERENCES stock("idStock") ON DELETE SET NULL,
    designation TEXT NOT NULL,
    quantite INTEGER NOT NULL CHECK (quantite > 0),
    type_sortie VARCHAR(20) NOT NULL CHECK (type_sortie IN ('examen_patient', 'usage_interne')),
    utilisateur_id INTEGER REFERENCES utilisateurs(id) ON DELETE SET NULL,
    patient_id INTEGER REFERENCES patients(id),
    examen_id INTEGER REFERENCES examens_complementaires(id) ON DELETE SET NULL,
    motif TEXT,
    date_mouvement TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_mouvements_consommable_stock_id ON mouvements_consommable(stock_id);
CREATE INDEX idx_mouvements_consommable_date ON mouvements_consommable(date_mouvement);

-- 4. Droits applicatifs (table créée par postgres ; la séquence est couverte par le
--    ALTER DEFAULT PRIVILEGES de la Phase 17, GRANT explicite par sécurité).
GRANT SELECT, INSERT, UPDATE, DELETE ON mouvements_consommable TO cabinet_user;
GRANT USAGE, SELECT ON SEQUENCE mouvements_consommable_id_seq TO cabinet_user;

COMMIT;
