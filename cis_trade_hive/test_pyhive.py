#!/usr/bin/env python
"""Test PyHive connection"""

from pyhive import hive

print("Testing PyHive connection with auth=NONE...")
print("Connecting to localhost:10000, database: cis, auth: NONE")

try:
    conn = hive.Connection(
        host='localhost',
        port=10000,
        database='cis',
        auth='NONE'
    )
    print("Connection successful!")

    cursor = conn.cursor()
    print("Cursor created!")

    # Test 1: Simple query
    cursor.execute("SELECT 1 as test")
    result = cursor.fetchone()
    print(f"Test query result: {result}")

    # Test 2: Query with parameter
    query_param = """
        SELECT cis_user_id, login, name, email
        FROM cis_user
        WHERE UPPER(login) = UPPER(%s)
          AND is_deleted = 'false'
          AND enabled = 'true'
    """
    cursor.execute(query_param, ('TMP3RC',))
    user_result_param = cursor.fetchone()
    print(f"User query (with param) result: {user_result_param}")

    # Test 3: Query without parameter (hard-coded)
    query_hardcoded = """
        SELECT cis_user_id, login, name, email
        FROM cis_user
        WHERE UPPER(login) = 'TMP3RC'
          AND is_deleted = false
          AND enabled = true
    """
    cursor.execute(query_hardcoded)
    user_result_hardcoded = cursor.fetchone()
    print(f"User query (hard-coded) result: {user_result_hardcoded}")

    cursor.close()
    conn.close()
    print("Test completed successfully!")

except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
