-- =====================================================
-- Sample Currency Data for CisTrade
-- =====================================================

INSERT INTO reference_currency (code, name, full_name, symbol, decimal_places, rate_precision, calendar, spot_schedule, is_active, is_base_currency, created_at) VALUES
('USD', 'US Dollar', 'United States Dollar', '$', 2, 6, 'USD', 'T+2', TRUE, TRUE, CURRENT_TIMESTAMP),
('EUR', 'Euro', 'European Euro', '€', 2, 6, 'EUR', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('GBP', 'British Pound', 'Great Britain Pound Sterling', '£', 2, 6, 'GBP', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('JPY', 'Japanese Yen', 'Japanese Yen', '¥', 0, 4, 'JPY', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('SGD', 'Singapore Dollar', 'Singapore Dollar', 'S$', 2, 6, 'SGD', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('AUD', 'Australian Dollar', 'Australian Dollar', 'A$', 2, 6, 'AUD', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('CAD', 'Canadian Dollar', 'Canadian Dollar', 'C$', 2, 6, 'CAD', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('CHF', 'Swiss Franc', 'Swiss Franc', 'CHF', 2, 6, 'CHF', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('CNY', 'Chinese Yuan', 'Chinese Yuan Renminbi', '¥', 2, 6, 'CNY', 'T+1', TRUE, FALSE, CURRENT_TIMESTAMP),
('HKD', 'Hong Kong Dollar', 'Hong Kong Dollar', 'HK$', 2, 6, 'HKD', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('NZD', 'New Zealand Dollar', 'New Zealand Dollar', 'NZ$', 2, 6, 'NZD', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('SEK', 'Swedish Krona', 'Swedish Krona', 'kr', 2, 6, 'SEK', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('NOK', 'Norwegian Krone', 'Norwegian Krone', 'kr', 2, 6, 'NOK', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('DKK', 'Danish Krone', 'Danish Krone', 'kr', 2, 6, 'DKK', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('INR', 'Indian Rupee', 'Indian Rupee', '₹', 2, 6, 'INR', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('MYR', 'Malaysian Ringgit', 'Malaysian Ringgit', 'RM', 2, 6, 'MYR', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('THB', 'Thai Baht', 'Thai Baht', '฿', 2, 6, 'THB', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('KRW', 'Korean Won', 'South Korean Won', '₩', 0, 4, 'KRW', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('PHP', 'Philippine Peso', 'Philippine Peso', '₱', 2, 6, 'PHP', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('IDR', 'Indonesian Rupiah', 'Indonesian Rupiah', 'Rp', 0, 4, 'IDR', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('ZAR', 'South African Rand', 'South African Rand', 'R', 2, 6, 'ZAR', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('BRL', 'Brazilian Real', 'Brazilian Real', 'R$', 2, 6, 'BRL', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('MXN', 'Mexican Peso', 'Mexican Peso', '$', 2, 6, 'MXN', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('TRY', 'Turkish Lira', 'Turkish Lira', '₺', 2, 6, 'TRY', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP),
('RUB', 'Russian Ruble', 'Russian Ruble', '₽', 2, 6, 'RUB', 'T+2', TRUE, FALSE, CURRENT_TIMESTAMP);
