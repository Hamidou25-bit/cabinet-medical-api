-- Phase : gestion des types de stock (table dédiée, distincte de la colonne categorie
-- existante depuis la Phase 16). categorie ('medicament'/'materiel') reste la source de
-- vérité pour les 2 volets de la page Stock et l'autocomplete des ordonnances : chaque
-- type_stock est associé à l'une des deux, ce qui permet au champ "Type" du formulaire
-- (désormais une liste déroulante) de piloter automatiquement le bon volet à l'enregistrement.

-- unaccent : nécessaire pour comparer "Type" (texte libre historique, variantes sans accent
-- type "Medicament") au libellé type_stock sans faux négatif lors de la vérification d'usage
-- avant suppression d'un type.
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS type_stock (
    id SERIAL PRIMARY KEY,
    libelle VARCHAR(100) UNIQUE NOT NULL,
    categorie VARCHAR(20) NOT NULL CHECK (categorie IN ('medicament', 'materiel'))
);

INSERT INTO type_stock (libelle, categorie) VALUES
    ('Médicament', 'medicament'),
    ('Matériel médical', 'materiel')
ON CONFLICT (libelle) DO NOTHING;
