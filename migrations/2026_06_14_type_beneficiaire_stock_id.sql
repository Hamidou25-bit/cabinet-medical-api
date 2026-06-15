-- Type de beneficiaire des ordonnances + lien ligne_ordonnance <-> stock
-- Remplace is_interne (booleen) par type_beneficiaire ('patient'|'tiers'|'interne'),
-- ce qui permet de distinguer les ordonnances pour un tiers (sans patient_id) des
-- ordonnances internes au cabinet. patient_id devient optionnel pour ces cas.
-- Ajoute le lien entre une ligne d'ordonnance et l'article de stock correspondant,
-- utilise pour determiner si une ligne genere une sortie de stock (donc une recette).

ALTER TABLE ligne_ordonnance
    ADD COLUMN stock_id INTEGER REFERENCES stock("idStock") ON DELETE SET NULL;

CREATE INDEX idx_ligne_ordonnance_stock_id ON ligne_ordonnance(stock_id);

ALTER TABLE ordonnance
    ADD COLUMN type_beneficiaire TEXT NOT NULL DEFAULT 'patient'
    CHECK (type_beneficiaire IN ('patient', 'tiers', 'interne'));

ALTER TABLE ordonnance
    ALTER COLUMN patient_id DROP NOT NULL;
