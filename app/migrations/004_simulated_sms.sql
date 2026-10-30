BEGIN;
CREATE TABLE IF NOT EXISTS simulated_sms (
    id BIGSERIAL PRIMARY KEY,
    recipient VARCHAR(15) NOT NULL,
    message TEXT NOT NULL,
    sent_at DOUBLE PRECISION NOT NULL,
    delivery_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_simulated_sms_recipient ON simulated_sms(recipient, id);
COMMIT;
