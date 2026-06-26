-- Table de répartition des recettes entre cabinet / médecin / laborantin,
-- calculée et figée (snapshot des taux) à chaque encaissement.
CREATE TABLE IF NOT EXISTS repartition_recettes (
    id SERIAL PRIMARY KEY,
    reference_type VARCHAR(20) NOT NULL CHECK (reference_type IN ('consultation', 'soin', 'examen', 'ordonnance')),
    reference_id INTEGER NOT NULL,
    montant_total NUMERIC(10,2) NOT NULL,
    part_cabinet NUMERIC(10,2) NOT NULL DEFAULT 0,
    part_medecin NUMERIC(10,2) NOT NULL DEFAULT 0,
    part_laborantin NUMERIC(10,2) NOT NULL DEFAULT 0,
    taux_cabinet NUMERIC(5,2) NOT NULL,
    taux_medecin NUMERIC(5,2) NOT NULL DEFAULT 0,
    taux_laborantin NUMERIC(5,2) NOT NULL DEFAULT 0,
    -- medecin_id réfère medecin(id) ; laborantin_id réfère utilisateurs(id) - deux
    -- tables différentes selon le type d'acte, pas de FK déclarée (même convention
    -- que consultations.medecin_id / ordonnance.medecin_id, non contraints non plus)
    medecin_id INTEGER,
    laborantin_id INTEGER,
    medecin_verse BOOLEAN NOT NULL DEFAULT FALSE,
    medecin_verse_le TIMESTAMP,
    laborantin_verse BOOLEAN NOT NULL DEFAULT FALSE,
    laborantin_verse_le TIMESTAMP,
    date_acte DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (reference_type, reference_id)
);

CREATE INDEX IF NOT EXISTS idx_repartition_medecin ON repartition_recettes(medecin_id);
CREATE INDEX IF NOT EXISTS idx_repartition_laborantin ON repartition_recettes(laborantin_id);
CREATE INDEX IF NOT EXISTS idx_repartition_date ON repartition_recettes(date_acte DESC);

-- Taux personnalisés par médecin (consultation) ou par laborantin (examen),
-- remplaçant le taux global de parametres_cabinet pour cette personne.
-- cible_id réfère medecin(id) si type_acte='consultation', utilisateurs(id) si type_acte='examen'.
CREATE TABLE IF NOT EXISTS taux_personnalises (
    id SERIAL PRIMARY KEY,
    type_acte VARCHAR(20) NOT NULL CHECK (type_acte IN ('consultation', 'examen')),
    cible_id INTEGER NOT NULL,
    taux_personnel NUMERIC(5,2) NOT NULL,
    actif BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (type_acte, cible_id)
);

INSERT INTO parametres_cabinet (cle, valeur, description) VALUES
('taux_cabinet_consultation', '50', 'Part cabinet sur consultation (%)'),
('taux_medecin_consultation', '50', 'Part médecin sur consultation (%)'),
('taux_cabinet_examen', '50', 'Part cabinet sur examen (%)'),
('taux_medecin_examen', '20', 'Part médecin (prescripteur) sur examen (%)'),
('taux_laborantin_examen', '30', 'Part laborantin sur examen (%)')
ON CONFLICT (cle) DO NOTHING;
