"""Deploy remaining files + restart."""
import paramiko, os, json, urllib.request, sys

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

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
sftp = ssh.open_sftp()

files = [
    'app.py',
    'data/gifts.json',
    'templates/slots.html',
    'templates/market.html',
    'templates/cases.html',
    'templates/scratch.html',
    'templates/pvp.html',
    'templates/inventory.html',
    'templates/games.html',
    'static/js/crash.js',
    'static/css/crash.css',
    'static/gifs/slots/cake.gif',
    'static/gifs/slots/car.gif',
    'static/gifs/slots/cigar.gif',
    'static/gifs/slots/cinema.gif',
    'static/gifs/slots/clown.gif',
    'static/img/slots/bear.png',
    'static/img/slots/book.png',
    'static/img/slots/calendar.png',
    'static/img/slots/candle.png',
    'static/img/slots/diamond.png',
    'static/img/slots/rocket.png',
    'static/img/gifts/clown_bear.gif',
]

for rel in files:
    local_path = os.path.join(LOCAL, rel.replace('/', os.sep))
    remote_path = REMOTE + '/' + rel
    # Ensure remote directory exists (recursive)
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
    print(f'Uploaded: {rel}', flush=True)

sftp.close()

stdin, stdout, stderr = ssh.exec_command('systemctl restart lunagifts')
stdout.channel.recv_exit_status()
print('Restarted gunicorn', flush=True)

stdin, stdout, stderr = ssh.exec_command('systemctl is-active lunagifts')
status = stdout.read().decode().strip()
print(f'Service status: {status}', flush=True)

stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
code = stdout.read().decode().strip()
print(f'/ HTTP status: {code}', flush=True)

ssh.close()
print('Deploy complete!')
