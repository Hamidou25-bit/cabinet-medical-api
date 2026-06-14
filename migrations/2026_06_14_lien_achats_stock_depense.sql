-- Lien Achats <-> Stock <-> Depenses
-- Ajoute la tracabilite entre une ligne d'achat, l'article de stock correspondant,
-- et la depense generee automatiquement pour l'achat.

ALTER TABLE lignes_achat
    ADD COLUMN stock_id INTEGER REFERENCES stock("idStock") ON DELETE SET NULL;

ALTER TABLE depense
    ADD COLUMN achat_id INTEGER REFERENCES achats(id) ON DELETE SET NULL;

CREATE INDEX idx_lignes_achat_stock_id ON lignes_achat(stock_id);
CREATE INDEX idx_depense_achat_id ON depense(achat_id);

INSERT INTO type_depense (nom)
SELECT 'Achats Fournisseurs'
WHERE NOT EXISTS (SELECT 1 FROM type_depense WHERE nom = 'Achats Fournisseurs');
