import paramiko, urllib.request, json, os

TW_TOKEN = os.environ.get('TW_TOKEN', '')
req = urllib.request.Request(
    'https://api.timeweb.cloud/api/v1/servers/7173011',
    headers={'Authorization': f'Bearer {TW_TOKEN}'}
)
data = json.loads(urllib.request.urlopen(req, timeout=10).read())
PASSWORD = data['server']['root_pass']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('72.56.242.231', username='root', password=PASSWORD, timeout=15)

_, o, _ = ssh.exec_command('systemctl is-active lunagifts')
print('Service:', o.read().decode().strip())

_, o, e = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/crash')
print('HTTP /crash:', o.read().decode().strip())

_, o, _ = ssh.exec_command('journalctl -u lunagifts --no-pager -n 10')
print('Last logs:')
print(o.read().decode())

ssh.close()
