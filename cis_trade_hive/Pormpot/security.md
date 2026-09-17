1. Now we need to design the logic for the Security.
2. Need to create main link Security under that we should have list of security with pagination, must have horizontal scroll for all the columns if it's going beyond the view . create/edit page, dashboard. 
   3. Below should be form datatype

             1. Security Name  - Text
             2. ISIN   - Text
             3. Security Description  - Text
             4. Issuer  -Dropdown (The Issuer column is dropdown and value should come from table gmp_cis_sta_dly_counterparty "Counterparty Name" column value where Issuer==Y)
             5. Industry  -Dropdown from UDF setup
             6. Country of Incorporation  Dropdown from UDF setup
             7. Shares Outstanding  -Text
             8. Country of Exchange  -Dropdown (The Country of Exchange Column is dropdown and value should come from  table gmp_cis_sta_dly_country "full_name")
             9. Exchange Code  --Text
             10. Currency Code  --Dropdown(The Currency Code column is dropdown and value should come from table gmp_cis_sta_dly_currency "curr_name")
             11. Ticker  -- Text
             12. Quoted / Unquoted  -- Dropdown from UDF setup
             13. Security Type  -- Dropdown from UDF setup
             14. Investment Type   -- Dropdown from UDF setup
             15. Price Date  -- Date
             16. Price  -- Text
             17. Price Source  --Dropdown from UDF setup
             18. Country of Issue  -- Dropdown from UDF setup
             19. Country of Primary Exchange  -- Dropdown from UDF setup
             20. Beta  -- Text
             21. BWCIIF  --Dropdown from UDF setup
             22. BWCIIF Others  --Dropdown from UDF setup
             23. CELS  --Text
             24. Issuer Type  --Dropdown from UDF setup 
             25. % Shareholding Entity 1   --Text
             26. % Shareholding Entity 2   -Text
             27. % Shareholding Entity 3   --Text
             28. % Shareholding Aggregated  --Text
             29. Approved S32  -Dropdown from UDF setup
             30. BASEL IV - FUND  -Dropdown from UDF setup
             31. Business Unit Head  -Dropdown from UDF setup
             32. Core/Non-core  -Dropdown from UDF setup
             33. Fund / Index Fund  -Dropdown from UDF setup
             34. Management Limit Classification  -Dropdown from UDF setup
             35. MAS 643 Entity Type  -Dropdown from UDF setup
             36. Person In Charge  -Dropdown from UDF setup
             37. Substantial >10%  -Dropdown from UDF setup
             38. Relative Index  -Dropdown from UDF setup
             39. Fin/Non-fin IND  -Dropdown from UDF setup
             40. MAS 6D Code  --Text
             41. PAR Value  --Text

4. The create /edit, should have parent and child approach. The main page should have this fields Security Name,ISIN,Security Description,Issuer,Industry,

   Country of Incorporation,Shares Outstanding,Country of Exchange,Exchange Code,Currency Code,Ticker,Quoted / Unquoted,Security Type,Investment Type. Create two hyderlink/button to go other fields and add info for other columns in cis_security_kudu tables.
   Use the form where the data store/hold from child to parent page till save/edit.
    
4. Each action should be audited with the audit table
5. Main Application Dashboard will have statistics info on Available Modules and link like others.
6. Keep ACL annotation and make this comments out like other, as this is demo/test for dev
7. Will have unit test 