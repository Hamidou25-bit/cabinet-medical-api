CREATE TABLE IF NOT EXISTS vaccinations (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    vaccin VARCHAR(100) NOT NULL,
    date_administration DATE NOT NULL,
    dose VARCHAR(50),
    prochain_rappel DATE,
    observations TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
