# LAN TLS for classroom deployment

**Status:** updated 2026-08-22. Host mode now performs certificate generation and starts a
dedicated HTTPS listener automatically. Use **Settings → Host mode** and the URL/QR shown there;
certificates live under `data/share-certs/` and the default join port is `8443`. The manual nginx
instructions below remain useful only for deployments that deliberately terminate TLS in nginx.

## Why this is not optional: the voice loop is dead on plain HTTP over the LAN

The flagship features — the mic (`getUserMedia`) and the voice WebSocket
(`WS /v1/audio/voice`) — only run in a browser **secure context**. Browsers grant a secure
context to `https://…` and, as a special case, to `http://localhost` / `http://127.0.0.1`.
They do **not** grant it to `http://<lan-ip>` or `http://<hostname>`.

So the moment a student opens the tutor from another device on the classroom Wi-Fi —
`http://192.168.1.50:3000` — the browser silently refuses the microphone and the voice loop
is gone. It works only on the host laptop itself (`localhost`), which is not the deployment.
Text chat still works over plain HTTP; **voice does not**. That is the whole reason to serve
HTTPS on the LAN.

We cannot use a public CA (Let's Encrypt et al.) — the box is offline and has no public
DNS name. The fix is a **local CA** we create ourselves, install once on each device, and
use to sign a server certificate for the laptop's LAN address. Fully offline, no external CA.

## The three steps

### 1. Generate the CA + server certificate (on the host laptop)

Pass the laptop's LAN IP and any hostnames students will type. `localhost`, `127.0.0.1`
and `::1` are always included.

```bash
# find the LAN IP first, e.g.:  ip -4 addr show | grep inet
./scripts/gen_local_tls.sh 192.168.1.50 tutor.local
```

This writes `certs/`:

| file | goes where | secret? |
|---|---|---|
| `rootCA.pem` | installed on **every student device** (the trust anchor) | no |
| `rootCA.key` | stays on the host; only used to issue more certs | **YES — never ship** |
| `fullchain.pem` | nginx: `/etc/nginx/certs/fullchain.pem` | no |
| `privkey.pem` | nginx: `/etc/nginx/certs/privkey.pem` | **YES — never ship** |

The script prints the CA's **SHA-256 fingerprint**. Write it down — you compare it on each
device after install so you know you trusted the right CA and not a look-alike.

Re-running the script **reuses the existing CA** and just re-issues the server cert, so you
can add a second laptop's IP later without re-trusting the CA on every phone. `--force`
recreates the CA from scratch — only do that if you accept re-installing it everywhere.

Cert lifetimes are deliberate: the CA is valid 10 years, the **server cert 825 days**
(Safari/iOS reject any TLS leaf cert valid longer than that, local CA or not). Renew the
server cert before it expires by re-running the script; the CA and its device trust stay put.

> If `mkcert` happens to be installed the script points you at it, but it stays on `openssl`:
> the classroom needs an explicit, portable `rootCA.pem` to hand to each device, which
> `openssl` emits directly (mkcert hides its CA behind `mkcert -CAROOT`).

### 2. Turn on TLS in nginx

`gen_local_tls.sh` writes certs the container expects at `/etc/nginx/certs/`. Two edits,
both already scaffolded:

- **Mount the certs.** In `docker-compose.yml`, under the `frontend` service:

  ```yaml
      volumes:
        - ./certs:/etc/nginx/certs:ro
  ```

- **Enable the 443 server block.** In `docker/nginx.conf.template`, uncomment the
  `listen 443 ssl` block at the bottom (and the `:80 → :443` redirect). The header set is
  the same one the `:80` server uses; keep it identical (the template extracts it to
  `/etc/nginx/snippets/muta-headers.conf`). Then redeploy:

  ```bash
  ./run.sh          # rebuilds the frontend image and restarts
  ```

The published port is still `3000` on the host (`docker-compose.yml` maps host `3000` →
container `80`/`443`). If you want the friendlier `https://<lan-ip>` with no port, map host
`443` → container `443` as well — the operator/lead engineer owns that compose edit.

Nothing about the `/v1` contract changes: the browser reaches the backend through the same
same-origin nginx proxy, now over TLS, so the WebSocket upgrades to `wss://` automatically
and there is still **no CORS** anywhere. The CSP already allows `connect-src … wss:`.

### 3. Install `rootCA.pem` on each device (one time per device)

Copy `certs/rootCA.pem` to the device (USB, a QR/link on the LAN, whatever is offline).
Then trust it:

- **Android (Chrome):** Settings → Security → *Encryption & credentials* → *Install a
  certificate* → *CA certificate* → pick `rootCA.pem`. Android warns the network may be
  monitored — expected for a private CA. (Some Android builds restrict user CAs to specific
  apps; if Chrome still rejects, use Firefox, which has its own store — next bullet.)
- **iOS / iPadOS (Safari):** open/AirDrop `rootCA.pem` → Settings → *Profile Downloaded* →
  Install. **Then** Settings → General → About → *Certificate Trust Settings* → toggle the
  Muta CA **on**. iOS will not trust it until that second toggle.
- **Firefox (any OS):** Firefox ignores the system store. Settings → *Privacy & Security* →
  *Certificates* → *View Certificates* → *Authorities* → *Import* → `rootCA.pem` → check
  *Trust this CA to identify websites*.
- **Ubuntu / Debian (system-wide, for Chromium too):**
  ```bash
  sudo cp certs/rootCA.pem /usr/local/share/ca-certificates/muta-local-ca.crt
  sudo update-ca-certificates
  ```
- **macOS (Safari/Chrome):** double-click `rootCA.pem` → Keychain Access → find "Muta Local
  Root CA" → *Get Info* → *Trust* → *When using this certificate: Always Trust*.

After install, open `https://192.168.1.50:3000`. No warning, a padlock, and the mic prompt
appears — voice works over the LAN. If you see a name-mismatch error, the address you typed
is not in the cert's SAN: re-run step 1 with that IP/hostname added.

## Troubleshooting

- **"Not secure" / mic still blocked:** you are on `http://`, not `https://`. Confirm the
  `:80 → :443` redirect is enabled, or type `https://` explicitly.
- **`NET::ERR_CERT_AUTHORITY_INVALID`:** the device has not trusted `rootCA.pem` yet
  (step 3), or trusts an older CA — compare the fingerprint the script printed.
- **`NET::ERR_CERT_COMMON_NAME_INVALID` / name mismatch:** the hostname/IP is not a SAN.
  Re-issue: `./scripts/gen_local_tls.sh 192.168.1.50 tutor.local <new-name>`.
- **Cert expired after ~2 years:** re-run the script (the CA and device trust are unaffected).

## What is a secret and what is not

`rootCA.pem` is public by design — it is *meant* to be copied to every device.
`rootCA.key` and `privkey.pem` are private keys: whoever holds `rootCA.key` can mint certs
every trusting device will accept, so it never leaves the host and never rides the flash
drive. The script writes both private keys `0600` and drops a `certs/.gitignore` (`*`) so
nothing under `certs/` is ever committed.
