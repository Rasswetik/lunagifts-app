"""One-shot deploy with embedded token."""
import paramiko, os, json, urllib.request

HOST = '72.56.242.231'
USER = 'root'
REMOTE = '/opt/lunagifts'
LOCAL = os.path.dirname(os.path.abspath(__file__))

TW_TOKEN = 'eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCIsImtpZCI6IjFrYnhacFJNQGJSI0tSbE1xS1lqIn0.eyJ1c2VyIjoid3E4MDU2MTAiLCJ0eXBlIjoiYXBpX2tleSIsImFwaV9rZXlfaWQiOiI2OTU3NzE0OS1mYTUyLTQzNTMtOTdjMC1iMTA2MzEzOWMwN2QiLCJpYXQiOjE3NzUxNDg4NjF9.uuV260IsMNbCAhoZeaJ_BjZ66slT4Z_3RMpgmT2_QLMtMobwSUJr6vCR7Ymw96pGT1iCcbuIVneaAwmvTplu72VtUc6bl5EEt9Q7YdcMCGgwqk7aTRBJowDxmISjpPahOTxTHHoPUHFabGIviMtbefTzrdgNs82wG-LG0JDlQjovOGdCETvOM0yBXeqHX71OPfdy4g5xKY3vVrYvcPL-t472OpnLiHSsF_wuzGFzNQBGjjJUrgtOCCZy6iPuy74vRqVjD7CiPoLI_UcCwg3ub4v4CxRHV53sTCYIaWPwHzCX96SRK9UFh7MaxOMq9letHtTlvppuONntaEKJrkmdzDW-eSfUCCAUlVFgph83ORavRZWGFF2dRASOzVsBJt4OMQxzRi4uIDr0pFHDbPL2lBD7i6oCDtWuF3-IZvlKfI7PapwFc7jNV9y1qbfKQyRfm3oGdHWwJ_lRAxf7oqm3knXqpMGM9bdkuUa8K2lmb0H2fUDWLYqL7KTH-dhw441k'

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
    print(f'OK: {rel}', flush=True)

sftp.close()
print('All files uploaded. Restarting...', flush=True)

stdin, stdout, stderr = ssh.exec_command('systemctl restart lunagifts')
stdout.channel.recv_exit_status()
print('Restarted gunicorn', flush=True)

stdin, stdout, stderr = ssh.exec_command('systemctl is-active lunagifts')
status = stdout.read().decode().strip()
print(f'Service: {status}', flush=True)

stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/')
code = stdout.read().decode().strip()
print(f'HTTP: {code}', flush=True)

ssh.close()
print('Deploy complete!')
