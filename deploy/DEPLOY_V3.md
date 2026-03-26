# wlbs-scan V3 Deployment

This deployment guide is for the standalone `wlbs_server.py` service only.
It does not touch unrelated applications or databases.

## Target

- Host: `111.231.112.127`
- Default hub port: `8765`
- Data directory: `/var/lib/wlbs-server`

## Install

```bash
git clone <repo> /opt/wlbs_scan
cd /opt/wlbs_scan
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[server]
```

## Configure

```bash
cp deploy/wlbs_server.env.example deploy/wlbs_server.env
```

Edit `deploy/wlbs_server.env` if you need to change the data directory or port.

## Run

```bash
. .venv/bin/activate
uvicorn wlbs_server:app --host 0.0.0.0 --port 8765 --workers 2
```

## systemd

Copy `deploy/wlbs_server.service` to `/etc/systemd/system/wlbs_server.service`,
then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wlbs_server
sudo systemctl start wlbs_server
sudo systemctl status wlbs_server
```

## Smoke checks

```bash
curl http://127.0.0.1:8765/health
curl -H "x-api-key: <key>" http://127.0.0.1:8765/account/status
```

## Important boundary

This server is file-backed and self-contained.
Do not point it at unrelated project databases or services.
