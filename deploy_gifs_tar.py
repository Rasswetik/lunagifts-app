"""Compress scratch GIFs, upload tar, extract on server."""
import paramiko, os, json, urllib.request, tarfile, tempfile

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

# Create tar with remaining GIFs
tar_path = os.path.join(tempfile.gettempdir(), 'scratch_gifs.tar.gz')
already_on_server = {'moon.gif', 'moon1.gif', 'moon2.gif', 'moon3.gif', 'moon4.gif', 'moon5.gif', 'moon6.gif'}
gif_dir = os.path.join(LOCAL, 'static', 'gifs', 'scratch')

print('Creating tar archive...', flush=True)
with tarfile.open(tar_path, 'w:gz') as tar:
    for fname in os.listdir(gif_dir):
        if fname.endswith('.gif') and fname not in already_on_server:
            fpath = os.path.join(gif_dir, fname)
            arcname = f'static/gifs/scratch/{fname}'
            tar.add(fpath, arcname=arcname)
            print(f'  Added {fname} ({os.path.getsize(fpath)/1024/1024:.1f}MB)', flush=True)

tar_size = os.path.getsize(tar_path) / (1024*1024)
print(f'Archive: {tar_size:.1f} MB', flush=True)

# Upload tar
print('Uploading tar...', flush=True)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
ssh.get_transport().set_keepalive(5)
sftp = ssh.open_sftp()
sftp.get_channel().settimeout(300)
sftp.put(tar_path, '/tmp/scratch_gifs.tar.gz')
sftp.close()
print('Uploaded tar OK', flush=True)

# Extract on server
print('Extracting on server...', flush=True)
stdin, stdout, stderr = ssh.exec_command(f'cd {REMOTE} && tar xzf /tmp/scratch_gifs.tar.gz && rm /tmp/scratch_gifs.tar.gz')
stdout.channel.recv_exit_status()
err = stderr.read().decode().strip()
if err:
    print(f'Tar extract stderr: {err}', flush=True)

# Restart
print('Restarting gunicorn...', flush=True)
stdin, stdout, stderr = ssh.exec_command('systemctl restart lunagifts')
stdout.channel.recv_exit_status()

import time
time.sleep(3)

stdin, stdout, stderr = ssh.exec_command('systemctl is-active lunagifts')
status = stdout.read().decode().strip()
print(f'Service: {status}', flush=True)

stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
code = stdout.read().decode().strip()
print(f'HTTP: {code}', flush=True)

stdin, stdout, stderr = ssh.exec_command('ls -la /opt/lunagifts/static/gifs/scratch/')
files = stdout.read().decode()
print(f'Scratch dir:\n{files}', flush=True)

ssh.close()
os.remove(tar_path)
print('Done!')
