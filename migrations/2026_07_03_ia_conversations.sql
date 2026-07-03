-- Migration Phase IA — Historique des conversations
-- À exécuter sur le serveur APRÈS pg_dump de sauvegarde
-- pg_dump cabinet_medical > /home/ubuntu/backups/avant_ia_historique_$(date +%Y%m%d_%H%M%S).sql

CREATE TABLE IF NOT EXISTS ia_conversations (
    id SERIAL PRIMARY KEY,
    utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    contenu TEXT NOT NULL,
    date_message TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ia_conv_utilisateur ON ia_conversations(utilisateur_id);
CREATE INDEX IF NOT EXISTS idx_ia_conv_date ON ia_conversations(date_message);

-- Vérification
-- SELECT COUNT(*) FROM ia_conversations;
