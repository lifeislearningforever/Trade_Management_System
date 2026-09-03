-- =====================================================
-- Sample Counterparty Data for CisTrade
-- =====================================================

INSERT INTO reference_counterparty (code, name, legal_name, short_name, counterparty_type, email, phone, city, country, status, is_active, risk_category, created_at) VALUES
-- Banks
('HSBC', 'HSBC Bank', 'The Hongkong and Shanghai Banking Corporation Limited', 'HSBC', 'BANK', 'corporate@hsbc.com', '+65-6227-8288', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('DBS', 'DBS Bank', 'DBS Bank Ltd', 'DBS', 'BANK', 'corporate@dbs.com', '+65-6878-8888', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('UOB', 'UOB Bank', 'United Overseas Bank Limited', 'UOB', 'BANK', 'corporate@uob.com.sg', '+65-6533-9898', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('OCBC', 'OCBC Bank', 'Oversea-Chinese Banking Corporation Limited', 'OCBC', 'BANK', 'corporate@ocbc.com', '+65-6363-3333', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('CITI', 'Citibank', 'Citibank N.A.', 'Citi', 'BANK', 'corporate@citi.com', '+65-6225-5225', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),

-- Brokers
('GS', 'Goldman Sachs', 'Goldman Sachs (Singapore) Pte', 'GS', 'BROKER', 'trading@gs.com', '+65-6889-1000', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('MS', 'Morgan Stanley', 'Morgan Stanley Asia (Singapore) Pte', 'MS', 'BROKER', 'trading@morganstanley.com', '+65-6834-6888', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('JPM', 'JP Morgan', 'J.P. Morgan Securities Singapore Private Limited', 'JPM', 'BROKER', 'trading@jpmorgan.com', '+65-6882-2888', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('BAML', 'Bank of America Merrill Lynch', 'Bank of America Merrill Lynch', 'BAML', 'BROKER', 'trading@baml.com', '+65-6678-0088', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'MEDIUM', CURRENT_TIMESTAMP),
('UBS', 'UBS AG', 'UBS AG Singapore Branch', 'UBS', 'BROKER', 'trading@ubs.com', '+65-6495-8000', 'Singapore', 'Singapore', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),

-- Corporates
('APPLE', 'Apple Inc', 'Apple Inc', 'Apple', 'CORPORATE', 'treasury@apple.com', '+1-408-996-1010', 'Cupertino', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('MSFT', 'Microsoft Corporation', 'Microsoft Corporation', 'Microsoft', 'CORPORATE', 'treasury@microsoft.com', '+1-425-882-8080', 'Redmond', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('GOOG', 'Google LLC', 'Google LLC', 'Google', 'CORPORATE', 'treasury@google.com', '+1-650-253-0000', 'Mountain View', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('AMZN', 'Amazon.com Inc', 'Amazon.com, Inc.', 'Amazon', 'CORPORATE', 'treasury@amazon.com', '+1-206-266-1000', 'Seattle', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('TSLA', 'Tesla Inc', 'Tesla, Inc.', 'Tesla', 'CORPORATE', 'treasury@tesla.com', '+1-512-516-8177', 'Austin', 'United States', 'ACTIVE', TRUE, 'MEDIUM', CURRENT_TIMESTAMP),

-- Institutional
('BROCK', 'BlackRock', 'BlackRock Investment Management', 'BlackRock', 'INSTITUTIONAL', 'client.service@blackrock.com', '+1-212-810-5300', 'New York', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('VANG', 'Vanguard', 'The Vanguard Group', 'Vanguard', 'INSTITUTIONAL', 'client@vanguard.com', '+1-610-669-1000', 'Valley Forge', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('FIDELITY', 'Fidelity Investments', 'Fidelity Management & Research Company', 'Fidelity', 'INSTITUTIONAL', 'institutional@fidelity.com', '+1-617-563-7000', 'Boston', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('STATE', 'State Street', 'State Street Global Advisors', 'State Street', 'INSTITUTIONAL', 'contact@ssga.com', '+1-617-786-3000', 'Boston', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP),
('PIMCO', 'PIMCO', 'Pacific Investment Management Company', 'PIMCO', 'INSTITUTIONAL', 'clientservices@pimco.com', '+1-949-720-6000', 'Newport Beach', 'United States', 'ACTIVE', TRUE, 'LOW', CURRENT_TIMESTAMP);
