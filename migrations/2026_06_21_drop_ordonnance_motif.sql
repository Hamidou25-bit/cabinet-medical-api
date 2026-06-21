-- Le champ Motif a ete retire du formulaire Ordonnances (remplace par Prescripteur,
-- cf. migration 2026_06_21_ordonnance_medecin_id.sql) et n'est plus lu/ecrit nulle
-- part dans le code. 3 ordonnances avaient une valeur renseignee (id 11 'Maladie',
-- id 13 'TTMT Tanti', id 31 'Dx ABDO') - suppression actee avec l'utilisateur.
ALTER TABLE ordonnance DROP COLUMN motif;
