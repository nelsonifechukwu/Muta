# Durable GCP native UI service

## Failure

The GCP native launcher was started with `nohup` from an SSH deployment command. The SSH session
ended, the launcher process disappeared, and its gateway and engine children survived as orphaned
processes. A later restart then failed its port preflight forever because those children still held
ports 8000 and 8080. The browser could consequently reach an old exported UI instead of the
revision containing `ui/math.js`, which made already-fixed equations appear broken again.

## Changes

1. Add a versioned systemd user unit for the GCP/native Linux topology. systemd owns the gateway
   and its supervised llama-server as one control group, restarts the stack as a unit, and starts it
   again after a VM reboot.
2. Send TERM to the gateway first so its lifespan stops the engine without racing the supervisor;
   retain a cgroup-wide final KILL as the orphan backstop.
3. Pin both listeners to loopback and clear the arbitrary engine-argument escape hatch in the
   executed command, then continue using an SSH tunnel; neither an environment-file nor repo
   `.env` override can expose them.
4. Document the PID-targeted takeover from the known orphan state, linger, health, logs, and safe
   restart commands in `RUN.md`.
5. Add static regression tests for service ownership, restart, signal, and bind-order invariants.

## Verification

- Run the focused service test, the full Python suite, UI math parser tests, JavaScript syntax
  checks, and `git diff --check`.
- Have a fresh adversarial reviewer inspect the service and tests.
- Commit and push once, synchronize the identical commit to GCP without touching benchmark output,
  install the unit, and prove it is enabled, active, and healthy after the deployment SSH command
  has exited.
- Load the exact reported conversation through the normal port-18001 SSH tunnel and verify KaTeX
  nodes are present while visible raw TeX commands are absent.
