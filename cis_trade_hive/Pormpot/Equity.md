Now we need to build the module Equity Price. This should come under Market Data.
We have to build CRUD pages, Create/Edit, list and update the dashboard with fx rate and Equity price
Create Kudu table with following details with audit columns info.
The Crate should work as when select the first dropdown the second value gets pdate bases on the pervious selected value
The columns are 1. Currency - --Dropdown(The Currency Code column is dropdown and value should come from table gmp_cis_sta_dly_currency "curr_name")
                2. Security_Label- Dropdown Currency Code column is dropdown and value should come from table cis_security "security_name")
                3. isin code - Dropdown Currency Code column is dropdown and value should come from table cis_security "isin")
                4. Date - Default today date
                5. Main closing price- Text
                6. Market - Dropdown from UDF setup
                7.Timestamp - Date and time
                8. Group - text
You should avoid creating any Django ORM, follow all SOILD design like FX rate in market