-- Phase 7 : la decrementation de stock pour une ordonnance doit etre declenchee
-- par la validation (est_validee), pas par la simple creation/modification.
-- stock_applique trace si le mouvement de stock a deja ete applique pour
-- l'ordonnance, afin d'eviter tout double mouvement et de pouvoir restaurer
-- le stock correctement en cas de devalidation/suppression.
--
-- Les ordonnances existantes ont deja eu leur stock decremente a la creation
-- (ancien comportement), donc on les marque toutes comme stock_applique = true,
-- puis on bascule le defaut a false pour les nouvelles ordonnances.
ALTER TABLE ordonnance ADD COLUMN stock_applique BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE ordonnance ALTER COLUMN stock_applique SET DEFAULT false;
