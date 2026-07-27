# Langfail Development Workflows

Running Langfail and validating exploits.

## Startup Commands
To run Langfail locally:
```bash
# Seed database
flask --app dvml seed
# Run REST application
flask --app dvml run
# Start background worker in another shell
flask --app dvml worker
```

## Running Exploit Proofs
Verify exploit paths by running:
```bash
# Verify SSRF to RCE chain
PYTHONPATH=. python exploits/chain_a_ssrf_to_rce.py
# Verify indirect prompt injection chain
PYTHONPATH=. python exploits/chain_b_indirect_injection.py
```
