-- Create Hive Database: cis
-- This script creates the main database for the CIS Trade Hive system

-- Create database if it doesn't exist
CREATE DATABASE IF NOT EXISTS cis
COMMENT 'CIS Trade Management System Database'
LOCATION '/user/hive/warehouse/cis.db';

-- Use the database
USE cis;

-- Show current database
SELECT current_database();

-- Verify database creation
SHOW DATABASES;
