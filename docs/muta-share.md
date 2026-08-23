# Muta Share (Host mode)

Muta Share lets one offline laptop serve independent tutor accounts to browsers on the same
local network. The model and all learner data remain on the host laptop.

## Host workflow

1. Start Muta with `./run.sh` or `./run.sh --native-linux`.
2. Open Muta on the laptop, open **Settings → Host mode**, and turn it on.
3. Choose a memory policy:
   - **ADTC competition** keeps the serving plan inside the competition RAM ceiling and runs
     at most two model replies at once. If the normal 4B model plus its paired image projector
     cannot fit safely under the official process-tree RSS rule, Muta atomically switches to
     the pinned local Qwen3.5 0.8B competition model and its own projector before opening the
     LAN listener.
   - **Use this system** measures physical, currently available and container/cgroup RAM,
     preserves useful context per chat, accounts for model weights and anonymous repacking,
     KV/recurrent state, prompt cache, compute buffers, the gateway and the selected model's
     projector,
     then caps simultaneous replies by physical CPU cores. Remaining replies wait in a bounded,
     fair queue. If other applications leave too little headroom, Muta asks the host to close
     them instead of expanding into swap or global OOM.
4. Give learners the displayed HTTPS address or let them scan its QR code.
5. Accept or decline sign-up requests under **People**. Removing an approved learner revokes
   every session, stops their queued/running work, and deletes their conversations,
   attachments, resources, settings, KV snapshots and learning twin.

Turning Host mode off preserves approved accounts and learner data, but revokes member sessions.
When it is turned on again, approved learners can log in without another approval. A removed or
declined username can sign up again and must be approved again.

## Learner workflow

1. Join the same Wi-Fi or Ethernet network and open the host's HTTPS URL.
2. Log in, or choose **Sign up**. A new sign-up waits on the page until the host accepts it.
3. Once approved, Muta opens automatically. Conversations, uploads, settings and the learning
   twin are private to that account and persist after logout.

Member accounts cannot enable Host mode, select/restart the shared model, view the host roster,
or use internal/diagnostic routes. They retain the learner features: text and voice chat,
image input, personal files/RAG, conversation history, tutor modes and learning preferences.

## First-device HTTPS trust

Passwords and session cookies are never accepted over plain LAN HTTP. Host mode creates an
offline local certificate authority under `data/share-certs/` and serves the app on port 8443.
For a warning-free secure connection (and browser microphone access), install `rootCA.pem` once
on each learner device. The host can download it from Host mode and distribute that public
certificate by USB/AirDrop; compare the SHA-256 fingerprint shown in Settings before trusting it.
Never distribute `rootCA.key` or `privkey.pem`.

Platform-specific certificate installation is documented in [tls-lan.md](tls-lan.md). Host mode
reuses the CA across restarts and reissues the leaf certificate for current LAN addresses.

## Persistence and recovery

- Share accounts/sessions/control state: `data/muta-share.sqlite3` (WAL, file mode 0600).
- LAN CA and server certificate: `data/share-certs/` (private keys mode 0600).
- Compose mounts `./data:/app/data`; rebuilding or recreating the backend does not discard them.
- Passwords use salted scrypt hashes. Session and enrollment secrets are stored only as SHA-256
  digests. Member sessions have a 24-hour idle limit and 30-day absolute limit.
- Account deletion is a resumable saga. If the process stops mid-delete, the account remains
  revoked in `deleting` state and cleanup resumes on the next product start.

## Capacity changes

Changing the memory policy may require a llama-server restart because `--parallel` and total
context are engine-start parameters. Muta refuses the change while a reply is running, queued or
reserved; finish or stop it and retry. Selecting/uploading an image runs no model and therefore
does not block replacement. Model and capacity replacement are one idle, rollback-safe
transition. A failed restart restores the previous model and serving profile.
The product-mode container ceiling is derived at startup from 85% of host RAM; that cgroup is the
single system reserve rather than applying 85% twice. Override it explicitly with
`MUTA_BACKEND_MEMORY_LIMIT` when required.

`./run.sh` also detects the laptop's LAN address before Docker starts; a container otherwise sees
only its unreachable bridge address. Native starts prefer the physical default-route interface
over Docker/VPN bridges and list alternatives; set `MUTA_SHARE_HOST=192.168.x.x` to override an
unusual route. Muta refuses to advertise a container bridge address when the injected host value
is unavailable.
