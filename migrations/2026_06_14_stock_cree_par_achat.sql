-- Annulation d'achat : suppression des articles de stock crees "fantomes"
-- Ajoute un flag sur lignes_achat pour savoir si la ligne a provoque la
-- creation d'un nouvel article de stock (vs. mise a jour d'un article existant).
-- Les lignes existantes restent a false (comportement actuel preserve pour l'historique).

ALTER TABLE lignes_achat
    ADD COLUMN stock_cree BOOLEAN NOT NULL DEFAULT false;
