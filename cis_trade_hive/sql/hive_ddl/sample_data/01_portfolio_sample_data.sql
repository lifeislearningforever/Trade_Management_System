-- ================================================================
-- Sample Portfolio Data for Hive ORC + ACID Tables
-- Database: gmp_cis
-- ================================================================

USE gmp_cis;

-- ================================================================
-- Insert sample portfolios with various statuses
-- ================================================================

INSERT INTO cis_portfolio VALUES
('PF001', 'GLOBAL_EQUITY', 'Global Equity Fund', 'EQUITY', 'USD', 'USD', 'John Smith', 'State Street', '2020-01-15', 'Global diversified equity portfolio', 'ACTIVE', true, '2024-01-01 00:00:00', 'system', '2024-01-01 00:00:00', 'system', NULL),
('PF002', 'ASIA_BOND', 'Asia Pacific Bond Fund', 'FIXED_INCOME', 'SGD', 'SGD', 'Jane Doe', 'HSBC', '2019-06-01', 'Asian fixed income portfolio', 'ACTIVE', true, '2024-01-01 00:00:00', 'system', '2024-01-01 00:00:00', 'system', NULL),
('PF003', 'US_GROWTH', 'US Growth Portfolio', 'EQUITY', 'USD', 'USD', 'Mike Johnson', 'JP Morgan', '2021-03-15', 'US growth stocks portfolio', 'PENDING_APPROVAL', false, '2024-01-15 00:00:00', 'maker1', '2024-01-15 00:00:00', 'maker1', NULL),
('PF004', 'EMEA_VALUE', 'EMEA Value Fund', 'EQUITY', 'EUR', 'EUR', 'Sarah Wilson', 'BNP Paribas', '2022-01-01', 'European value investment fund', 'DRAFT', false, '2024-02-01 00:00:00', 'maker2', '2024-02-01 00:00:00', 'maker2', NULL),
('PF005', 'GLOBAL_MULTI', 'Global Multi-Asset', 'MULTI_ASSET', 'USD', 'USD', 'David Brown', 'Citi', '2018-09-01', 'Multi-asset allocation portfolio', 'APPROVED', false, '2024-01-20 00:00:00', 'maker1', '2024-01-25 00:00:00', 'checker1', NULL),
('PF006', 'JAPAN_EQUITY', 'Japan Equity Fund', 'EQUITY', 'JPY', 'JPY', 'Takeshi Yamamoto', 'Nomura', '2020-04-01', 'Japanese equity portfolio', 'ACTIVE', true, '2023-06-01 00:00:00', 'system', '2023-12-01 00:00:00', 'system', NULL),
('PF007', 'CHINA_TECH', 'China Technology Fund', 'EQUITY', 'CNY', 'CNY', 'Wei Chen', 'ICBC', '2021-08-01', 'Chinese technology stocks', 'INACTIVE', false, '2023-08-01 00:00:00', 'maker1', '2024-01-01 00:00:00', 'checker1', NULL),
('PF008', 'INDIA_GROWTH', 'India Growth Portfolio', 'EQUITY', 'INR', 'INR', 'Raj Patel', 'HDFC', '2022-06-15', 'Indian equity growth fund', 'REJECTED', false, '2024-02-01 00:00:00', 'maker2', '2024-02-05 00:00:00', 'checker1', NULL),
('PF009', 'UK_DIVIDEND', 'UK Dividend Fund', 'EQUITY', 'GBP', 'GBP', 'James Thompson', 'Barclays', '2019-03-01', 'UK dividend-focused portfolio', 'ACTIVE', true, '2023-03-01 00:00:00', 'system', '2024-01-15 00:00:00', 'system', NULL),
('PF010', 'EM_DEBT', 'Emerging Markets Debt', 'FIXED_INCOME', 'USD', 'USD', 'Maria Garcia', 'Deutsche Bank', '2020-11-01', 'Emerging market debt portfolio', 'PENDING_APPROVAL', false, '2024-02-10 00:00:00', 'maker3', '2024-02-10 00:00:00', 'maker3', NULL);

-- Verify data loaded
SELECT 'Portfolios loaded:' as metric, COUNT(*) as count FROM cis_portfolio;
SELECT portfolio_short_name, portfolio_name, status, is_active FROM cis_portfolio LIMIT 10;
