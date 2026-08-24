# GCP Host-mode LAN relay

Date: 2026-08-24

## Failure

Native Muta on GCP discovers `10.138.0.2` and advertises
`https://10.138.0.2:8443/chat/`. That is a Google VPC address, not an address on the
operator laptop's Wi-Fi. The existing SSH launch forwards only the operator gateway
(`127.0.0.1:18001 → GCP 127.0.0.1:8000`), so a phone on the laptop's LAN has no route to
the advertised learner listener.

Merely opening GCP firewall port 8443 would turn a LAN-only feature into an Internet-facing
service. It would also make the original same-network assumption false and expand the attack
surface without an explicit product decision.

## Fix

1. Add a laptop-side GCP relay launcher. It discovers or accepts the laptop's LAN IPv4,
   forwards the operator listener on loopback, and forwards the TLS learner listener bound only
   to that LAN address.
2. Start native Muta with `MUTA_SHARE_HOST=<laptop LAN IP>`. Host mode therefore issues its leaf
   certificate and QR for the address learners can actually reach.
3. Make an ordinary GCP launch fail closed instead of advertising its VPC address when no relay
   host was supplied.
4. Keep GCP ports closed. Both paths travel inside the authenticated SSH connection.
5. Make host authority listener-aware: requests arriving on `MUTA_SHARE_PORT` are never operator
   requests, even when SSH forwarding makes their peer address `127.0.0.1`.
6. Document that the ordinary operator-only tunnel is not a classroom relay and that phones must
   trust Muta's local CA once before opening the HTTPS URL.
7. When the operator explicitly supplies fleet configuration, pass the HTTPS collector origin in
   the remote launch command and the write-only key over SSH stdin. Never expose the key in the
   command line or dry-run output; telemetry remains inert until local consent is granted.

## Verification

- Shell syntax and dry-run command construction cover explicit LAN IP, VM, zone, ports and the
  two different bind scopes.
- HTTP security regression proves a loopback peer on the TLS learner port cannot mint a host
  session, including with a forged `Host: localhost` header.
- Existing direct-loopback and trusted-primary-listener host bootstrap tests remain green.
- Relay tests prove partial/invalid fleet configuration fails closed and dry-run never prints the
  supplied write-only key.
- Full suite, diff check and focused browser/QR validation run before review.
