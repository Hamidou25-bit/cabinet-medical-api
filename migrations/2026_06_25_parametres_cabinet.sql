CREATE TABLE IF NOT EXISTS parametres_cabinet (
    id SERIAL PRIMARY KEY,
    cle VARCHAR(100) UNIQUE NOT NULL,
    valeur TEXT,
    description VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO parametres_cabinet (cle, valeur, description) VALUES
('nom_cabinet', 'Cabinet Médical BabaMouneissa', 'Nom du cabinet affiché sur les reçus'),
('adresse_cabinet', 'Bamako, Mali', 'Adresse du cabinet'),
('telephone_cabinet', '', 'Téléphone du cabinet'),
('prix_consultation', '2000', 'Prix de la consultation en FCFA'),
('logo_cabinet', '', 'URL ou base64 du logo cabinet')
ON CONFLICT (cle) DO NOTHING;
