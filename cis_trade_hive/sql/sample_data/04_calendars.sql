-- =====================================================
-- Sample Calendar/Holiday Data for CisTrade
-- Singapore Exchange (SGX) Holidays for 2025
-- =====================================================

INSERT INTO reference_calendar (calendar_label, calendar_description, holiday_date, holiday_name, holiday_type, is_trading_day, is_settlement_day, exchange, created_at) VALUES
-- 2025 Holidays
('SGX', 'Singapore Exchange', '2025-01-01', 'New Year''s Day', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-01-29', 'Chinese New Year', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-01-30', 'Chinese New Year', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-03-31', 'Hari Raya Puasa', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-04-18', 'Good Friday', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-05-01', 'Labour Day', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-05-12', 'Vesak Day', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-06-06', 'Hari Raya Haji', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-08-09', 'National Day', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-10-20', 'Deepavali', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),
('SGX', 'Singapore Exchange', '2025-12-25', 'Christmas Day', 'PUBLIC', FALSE, FALSE, 'SGX', CURRENT_TIMESTAMP),

-- NYSE Holidays 2025
('NYSE', 'New York Stock Exchange', '2025-01-01', 'New Year''s Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-01-20', 'Martin Luther King Jr. Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-02-17', 'Presidents Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-04-18', 'Good Friday', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-05-26', 'Memorial Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-06-19', 'Juneteenth', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-07-04', 'Independence Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-09-01', 'Labor Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-11-27', 'Thanksgiving', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),
('NYSE', 'New York Stock Exchange', '2025-12-25', 'Christmas Day', 'PUBLIC', FALSE, FALSE, 'NYSE', CURRENT_TIMESTAMP),

-- LSE Holidays 2025
('LSE', 'London Stock Exchange', '2025-01-01', 'New Year''s Day', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-04-18', 'Good Friday', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-04-21', 'Easter Monday', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-05-05', 'Early May Bank Holiday', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-05-26', 'Spring Bank Holiday', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-08-25', 'Summer Bank Holiday', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-12-25', 'Christmas Day', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP),
('LSE', 'London Stock Exchange', '2025-12-26', 'Boxing Day', 'PUBLIC', FALSE, FALSE, 'LSE', CURRENT_TIMESTAMP);
