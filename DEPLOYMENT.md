# CityGML Browser Deployment Runbook

This runbook documents the production deployment used on this machine.

## Service Summary

- Service name: `csd-citygml-browser.service`
- App directory: `/home/csd-lab/Documents/github/citygmlbrowser`
- Runtime: `uvicorn` via local virtualenv
- Port: `5176`

## Verify Current Status

```bash
systemctl status csd-citygml-browser.service
systemctl is-enabled csd-citygml-browser.service
systemctl is-active csd-citygml-browser.service
```

## Common Operations

```bash
# Start
sudo systemctl start csd-citygml-browser.service

# Stop
sudo systemctl stop csd-citygml-browser.service

# Restart
sudo systemctl restart csd-citygml-browser.service

# Enable on boot
sudo systemctl enable csd-citygml-browser.service

# Disable on boot
sudo systemctl disable csd-citygml-browser.service
```

## Logs

```bash
# Recent logs
journalctl -u csd-citygml-browser.service -n 200 --no-pager

# Follow logs live
journalctl -u csd-citygml-browser.service -f
```

## Health Checks

```bash
curl -sS http://127.0.0.1:5176/api/v1/health
curl -s -o /dev/null -w 'root=%{http_code}\n' http://127.0.0.1:5176/
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:5176/api/v1/health
```

## Deploy Code Updates

Run from `/home/csd-lab/Documents/github/citygmlbrowser`:

```bash
# 1) Update source
git pull

# 2) Update Python deps (if requirements changed)
./.venv/bin/pip install -r requirements-api.txt

# 3) Update Node deps
npm install
npm run setup

# 4) Build frontend assets for FastAPI static serving
npm run build

# 5) Restart service
sudo systemctl restart csd-citygml-browser.service

# 6) Confirm status
systemctl is-active csd-citygml-browser.service
curl -sS http://127.0.0.1:5176/api/v1/health
```

## Service Unit Reference

Current service unit path on this machine:

```bash
/etc/systemd/system/csd-citygml-browser.service
```

If you edit the unit file, apply changes with:

```bash
sudo systemctl daemon-reload
sudo systemctl restart csd-citygml-browser.service
```

## Troubleshooting

### Port already in use

```bash
sudo lsof -i :5176
```

If another process is bound to `5176`, stop it, then restart the service.

### Service fails to start

```bash
systemctl status csd-citygml-browser.service --no-pager
journalctl -u csd-citygml-browser.service -n 200 --no-pager
```

### Frontend not updating after pull

Rebuild and restart:

```bash
npm run build
sudo systemctl restart csd-citygml-browser.service
```
