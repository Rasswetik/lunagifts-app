"""Quick deploy: upload changed crash game files and restart."""
import paramiko, os, sys

HOST = '72.56.242.231'
USER = 'root'
REMOTE = '/opt/lunagifts'
LOCAL = os.path.dirname(os.path.abspath(__file__))

def log(msg):
    print(msg, flush=True)

# Get password from TimeWeb API
import urllib.request, json
TW_TOKEN = os.environ.get('TW_TOKEN', '')
if TW_TOKEN:
    req = urllib.request.Request(
        'https://api.timeweb.cloud/api/v1/servers/7173011',
        headers={'Authorization': f'Bearer {TW_TOKEN}'}
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    PASSWORD = data['server']['root_pass']
else:
    PASSWORD = os.environ.get('TW_ROOT_PASS', '')

if not PASSWORD:
    log("ERROR: No password available. Set TW_TOKEN or TW_ROOT_PASS")
    sys.exit(1)

log(f"Connecting to {HOST}...")

files = [
    'app.py',
    'bot.py',
    'db_compat.py',
    'data/scratch.json',
    'data/gifts.json',
    'templates/cases.html',
    'templates/crash.html',
    'templates/games.html',
    'templates/index.html',
    'templates/inventory.html',
    'templates/market.html',
    'templates/pvp.html',
    'templates/referral.html',
    'templates/scratch.html',
    'templates/topup.html',
    'static/css/crash.css',
    'static/css/style.css',
    'static/js/app.js',
    'static/js/crash.js',
    'templates/slots.html',
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
sftp = ssh.open_sftp()

for rel in files:
    local_path = os.path.join(LOCAL, rel.replace('/', os.sep))
    remote_path = REMOTE + '/' + rel
    rdir = '/'.join(remote_path.split('/')[:-1])
    # Ensure all parent dirs exist
    parts = rdir.split('/')
    for i in range(1, len(parts) + 1):
        partial = '/'.join(parts[:i])
        if not partial:
            continue
        try:
            sftp.stat(partial)
        except FileNotFoundError:
            try:
                sftp.mkdir(partial)
            except:
                pass
    sftp.put(local_path, remote_path)
    log(f'Uploaded: {rel}')

sftp.close()

stdin, stdout, stderr = ssh.exec_command('systemctl restart lunagifts')
stdout.channel.recv_exit_status()
log('Restarted gunicorn')

stdin, stdout, stderr = ssh.exec_command('systemctl is-active lunagifts')
status = stdout.read().decode().strip()
log(f'Service status: {status}')

stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
code = stdout.read().decode().strip()
log(f'/ HTTP status: {code}')

ssh.close()
log('Deploy complete!')
