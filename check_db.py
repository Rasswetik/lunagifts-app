import paramiko, os, json, urllib.request

TW_TOKEN = os.environ.get('TW_TOKEN', '')
req = urllib.request.Request(
    'https://api.timeweb.cloud/api/v1/servers/7173011',
    headers={'Authorization': f'Bearer {TW_TOKEN}'}
)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
PASSWORD = data['server']['root_pass']

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('72.56.242.231', username='root', password=PASSWORD)

commands = [
    "curl -s http://127.0.0.1:8000/api/crash/status",
    "curl -s http://127.0.0.1:8000/api/crash/history",
]

for cmd in commands:
    print(f">>> {cmd}")
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out.strip())
    if err: print(f"STDERR: {err.strip()}")
    print()

c.close()
