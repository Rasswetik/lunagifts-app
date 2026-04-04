import paramiko, os, json, urllib.request

TW_TOKEN = os.environ.get('TW_TOKEN', '')
req = urllib.request.Request('https://api.timeweb.cloud/api/v1/servers/7173011', headers={'Authorization': f'Bearer {TW_TOKEN}'})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
PASSWORD = data['server']['root_pass']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('72.56.242.231', username='root', password=PASSWORD, timeout=30)

# Check crash.js has the O(1) formula
stdin, stdout, stderr = ssh.exec_command('grep "elapsedToMult" /opt/lunagifts/static/js/crash.js')
result = stdout.read().decode().strip()
print(f'elapsedToMult in crash.js: {"YES" if result else "NO"}')
if result:
    print(result[:200])

# Check app.py has the safe ensure_background_threads
stdin, stdout, stderr = ssh.exec_command('grep "start_background_threads.*in globals" /opt/lunagifts/app.py')
result = stdout.read().decode().strip()
print(f'\nSafe ensure_background_threads: {"YES" if result else "NO"}')
if result:
    print(result)

# Check crash.css has updated brightness
stdin, stdout, stderr = ssh.exec_command('grep "brightness(0.55)" /opt/lunagifts/static/css/crash.css')
result = stdout.read().decode().strip()
print(f'\nUpdated gift brightness: {"YES" if result else "NO"}')

ssh.close()
