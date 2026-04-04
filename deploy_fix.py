"""Upload app.py + remaining scratch GIFs, restart."""
import paramiko, os, json, urllib.request

HOST = '72.56.242.231'
USER = 'root'
REMOTE = '/opt/lunagifts'
LOCAL = os.path.dirname(os.path.abspath(__file__))

TW_TOKEN = os.environ.get('TW_TOKEN', '')
req = urllib.request.Request(
    'https://api.timeweb.cloud/api/v1/servers/7173011',
    headers={'Authorization': f'Bearer {TW_TOKEN}'}
)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
PASSWORD = data['server']['root_pass']

# Files to upload: app.py + remaining GIFs not yet on server
files = ['app.py']
# Check which GIFs are missing
all_gifs = [f'static/gifs/scratch/moon{s}.gif' for s in [''] + list(range(1, 13))]
already_uploaded = {'moon.gif', 'moon1.gif', 'moon2.gif', 'moon3.gif', 'moon4.gif'}
for g in all_gifs:
    basename = os.path.basename(g)
    if basename not in already_uploaded:
        files.append(g)

for rel in files:
    local_path = os.path.join(LOCAL, rel.replace('/', os.sep))
    remote_path = REMOTE + '/' + rel
    size_mb = os.path.getsize(local_path) / (1024*1024)
    print(f'Uploading {rel} ({size_mb:.1f} MB)...', end=' ', flush=True)
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    ssh.get_transport().set_keepalive(10)
    sftp = ssh.open_sftp()
    sftp.get_channel().settimeout(120)
    
    # Ensure dir exists
    rdir = '/'.join(remote_path.split('/')[:-1])
    parts = rdir.split('/')
    for i in range(2, len(parts) + 1):
        partial = '/'.join(parts[:i])
        try:
            sftp.stat(partial)
        except FileNotFoundError:
            try:
                sftp.mkdir(partial)
            except Exception:
                pass
    
    sftp.put(local_path, remote_path)
    print('OK', flush=True)
    sftp.close()
    ssh.close()

# Restart service
print('Restarting gunicorn...', flush=True)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
stdin, stdout, stderr = ssh.exec_command('systemctl restart lunagifts')
stdout.channel.recv_exit_status()
print('Restarted', flush=True)

import time
time.sleep(3)

stdin, stdout, stderr = ssh.exec_command('systemctl is-active lunagifts')
status = stdout.read().decode().strip()
print(f'Service: {status}', flush=True)

stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
code = stdout.read().decode().strip()
print(f'HTTP: {code}', flush=True)

stdin, stdout, stderr = ssh.exec_command('ls /opt/lunagifts/static/gifs/scratch/ | wc -l')
count = stdout.read().decode().strip()
print(f'Scratch GIFs on server: {count}', flush=True)

ssh.close()
print('Done!')
