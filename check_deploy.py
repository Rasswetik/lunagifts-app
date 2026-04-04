import paramiko, os, json, urllib.request

TW_TOKEN = os.environ.get('TW_TOKEN', '')
req = urllib.request.Request('https://api.timeweb.cloud/api/v1/servers/7173011', headers={'Authorization': f'Bearer {TW_TOKEN}'})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
PASSWORD = data['server']['root_pass']

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('72.56.242.231', username='root', password=PASSWORD, timeout=30)

stdin, stdout, stderr = ssh.exec_command('ls -la /opt/lunagifts/static/gifs/scratch/ && echo "---" && systemctl is-active lunagifts && curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
print(stdout.read().decode())
print(stderr.read().decode())
ssh.close()
