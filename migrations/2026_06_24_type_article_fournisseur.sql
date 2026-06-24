-- Liste gérable (ajout/suppression admin) des types d'article proposés sur la fiche
-- Fournisseur. fournisseur.type_article reste un champ texte libre (inchangé) ;
-- cette table alimente uniquement le select du formulaire, par simplicité (pas de FK).
CREATE TABLE IF NOT EXISTS type_article_fournisseur (
    id SERIAL PRIMARY KEY,
    libelle VARCHAR(100) UNIQUE NOT NULL
);

INSERT INTO type_article_fournisseur (libelle) VALUES
    ('Médicament'),
    ('Matériel médical')
ON CONFLICT (libelle) DO NOTHING;
