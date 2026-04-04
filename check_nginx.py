import paramiko, urllib.request, json, os

TW_TOKEN = os.environ.get('TW_TOKEN', '')
req = urllib.request.Request(
    'https://api.timeweb.cloud/api/v1/servers/7173011',
    headers={'Authorization': f'Bearer {TW_TOKEN}'}
)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
pw = data['server']['root_pass']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('72.56.242.231', username='root', password=pw, timeout=15)

cmds = [
    'ls /etc/nginx/sites-enabled/',
    'cat /etc/nginx/sites-enabled/lunagifts 2>/dev/null || cat /etc/nginx/sites-enabled/default',
    'tail -20 /var/log/nginx/error.log',
    'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/',
    'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/crash',
]

for cmd in cmds:
    print(f'\n=== {cmd} ===')
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out[:1500])
    if err: print('STDERR:', err[:500])

ssh.close()
