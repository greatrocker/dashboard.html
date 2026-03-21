import os

# 1. Update .env
env_path = '/home/crypto/exchange-monitor/.env'
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        env_content = f.read()
    new_env = env_content.replace('MSSQL_SERVER=172.26.0.1', 'MSSQL_SERVER=host.docker.internal,1433')
    # If it was already something else, try a more generic approach
    if 'MSSQL_SERVER' in new_env and 'host.docker.internal,1433' not in new_env:
         import re
         new_env = re.sub(r'MSSQL_SERVER=.*', 'MSSQL_SERVER=host.docker.internal,1433', new_env)
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(new_env)
    print('Updated .env')

# 2. Update Python files
py_files = ['/home/crypto/exchange-monitor/api_server.py', '/home/crypto/exchange-monitor/bybit_ticker.py']
for py_path in py_files:
    if os.path.exists(py_path):
        with open(py_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Add TrustServerCertificate=yes
        new_content = content.replace('Encrypt=no;', 'Encrypt=no;TrustServerCertificate=yes;')
        with open(py_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Updated {py_path}')
