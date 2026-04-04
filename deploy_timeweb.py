#!/usr/bin/env python3
"""Deploy LunaGifts to TimeWeb Cloud server via SSH/SFTP."""
import os, sys, time, stat
import paramiko

HOST = "72.56.242.231"
USER = "root"
PASSWORD = os.environ.get("TW_ROOT_PASS", "")
REMOTE_DIR = "/opt/lunagifts"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Files/dirs to upload
UPLOAD_ITEMS = [
    "app.py",
    "bot.py",
    "db_compat.py",
    "requirements.txt",
    "Procfile",
    "data",
    "static",
    "templates",
]

SKIP_PATTERNS = {".pyc", "__pycache__", ".git", "node_modules", ".env"}


def should_skip(name):
    return any(name.endswith(p) or name == p for p in SKIP_PATTERNS)


def sftp_mkdir_p(sftp, remote_dir):
    dirs_to_create = []
    d = remote_dir
    while True:
        try:
            sftp.stat(d)
            break
        except FileNotFoundError:
            dirs_to_create.append(d)
            d = os.path.dirname(d)
            if not d or d == "/":
                break
    for d in reversed(dirs_to_create):
        sftp.mkdir(d)


def upload_path(sftp, local_path, remote_path):
    if os.path.isfile(local_path):
        remote_dir = os.path.dirname(remote_path)
        sftp_mkdir_p(sftp, remote_dir)
        print(f"  PUT {local_path} -> {remote_path}")
        sftp.put(local_path, remote_path)
    elif os.path.isdir(local_path):
        sftp_mkdir_p(sftp, remote_path)
        for item in os.listdir(local_path):
            if should_skip(item):
                continue
            upload_path(
                sftp,
                os.path.join(local_path, item),
                remote_path + "/" + item,
            )


def run_cmd(ssh, cmd, timeout=120):
    print(f"  RUN: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    if out.strip():
        print(f"  OUT: {out.strip()[:500]}")
    if err.strip():
        print(f"  ERR: {err.strip()[:500]}")
    return rc, out, err


def main():
    if not PASSWORD:
        print("ERROR: TW_ROOT_PASS env var not set")
        sys.exit(1)

    print(f"Connecting to {HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    print("Connected!")

    # --- UPLOAD FILES ---
    print("\n=== Uploading project files ===")
    sftp = ssh.open_sftp()
    sftp_mkdir_p(sftp, REMOTE_DIR)
    for item in UPLOAD_ITEMS:
        local = os.path.join(PROJECT_DIR, item)
        remote = REMOTE_DIR + "/" + item
        if os.path.exists(local):
            upload_path(sftp, local, remote)
        else:
            print(f"  SKIP (not found): {item}")
    sftp.close()
    print("Upload complete!")

    # --- SETUP SERVER ---
    print("\n=== Setting up server ===")

    # Install system deps
    run_cmd(ssh, "apt-get update -qq && apt-get install -y -qq python3-venv python3-pip nginx certbot python3-certbot-nginx > /dev/null 2>&1", timeout=300)

    # Create venv and install deps
    run_cmd(ssh, f"cd {REMOTE_DIR} && python3 -m venv venv && ./venv/bin/pip install --upgrade pip -q && ./venv/bin/pip install -r requirements.txt -q", timeout=300)

    # Create systemd service
    service = f"""[Unit]
Description=LunaGifts Web App
After=network.target

[Service]
User=root
WorkingDirectory={REMOTE_DIR}
ExecStart={REMOTE_DIR}/venv/bin/gunicorn app:app --bind 127.0.0.1:8000 --timeout 120 --workers 1
Restart=always
RestartSec=5
Environment=WEBAPP_URL=https://lunagifts.fun

[Install]
WantedBy=multi-user.target
"""
    run_cmd(ssh, f"cat > /etc/systemd/system/lunagifts.service << 'SERVICEEOF'\n{service}SERVICEEOF")
    run_cmd(ssh, "systemctl daemon-reload && systemctl enable lunagifts && systemctl restart lunagifts")
    time.sleep(2)
    run_cmd(ssh, "systemctl status lunagifts --no-pager -l")

    # --- NGINX CONFIG ---
    print("\n=== Configuring Nginx ===")
    nginx_conf = """server {
    listen 80;
    server_name lunagifts.fun www.lunagifts.fun;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias """ + REMOTE_DIR + """/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
"""
    run_cmd(ssh, f"cat > /etc/nginx/sites-available/lunagifts << 'NGINXEOF'\n{nginx_conf}NGINXEOF")
    run_cmd(ssh, "ln -sf /etc/nginx/sites-available/lunagifts /etc/nginx/sites-enabled/lunagifts")
    run_cmd(ssh, "rm -f /etc/nginx/sites-enabled/default")
    run_cmd(ssh, "nginx -t")
    run_cmd(ssh, "systemctl reload nginx")

    # --- SSL ---
    print("\n=== Setting up SSL ===")
    run_cmd(ssh, "certbot --nginx -d lunagifts.fun -d www.lunagifts.fun --non-interactive --agree-tos --email admin@lunagifts.fun --redirect 2>&1 || echo 'certbot done with warnings'", timeout=120)

    # Final check
    print("\n=== Final check ===")
    run_cmd(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/")
    run_cmd(ssh, "systemctl status lunagifts --no-pager | head -5")

    ssh.close()
    print("\n=== DONE! Site should be live at https://lunagifts.fun ===")


if __name__ == "__main__":
    main()
