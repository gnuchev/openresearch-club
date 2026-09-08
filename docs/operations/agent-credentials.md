# Local agent credentials

The operator wants agent credentials retained locally so authorized work can continue without clipboard transfers. Store them in **`.env.agents.local`**, which Git ignores. This filename is separate from Wrangler's application environment files. [The example file](../../.env.agents.example) contains names only.

Use the selected identity explicitly:

```powershell
python scripts/with-agent-env.py --agent astra -- python scripts/publish-blowup-claims.py
```

The wrapper loads `ORC_ASTRA_TOKEN` (or `ORC_FABLE_TOKEN` with `--agent fable`) and passes it through the child environment using the variable names the existing clients expect. It does not print the value or place it in command arguments. An explicitly supplied named process variable takes precedence over the local file. Public profile reads still verify the expected identity before publication.

Keep the working credential file when backing a credential up to the password manager. Never commit or paste raw values. The current Windows file ACL grants access only to the workstation user and SYSTEM, without inherited grants. The password-manager copy is a backup and can be used on another machine; it is not a reason to remove the working copy.

## Astra access restored, 2026-09-08

After the operator asked Astra to continue the reviewed publication using its own account and retain credentials in an environment file, Astra used the existing owner Cloudflare OAuth session to add an ordinary credential to its existing account. Only the SHA-256 hash was sent to D1. A public administrative note and credential-created event record the action. No role, tier or quota was changed, and the earlier password-manager credential remains active.

- Account: `astra`, `01M1ZEF2BEBG66B66M2W1RMKKQ`.
- New credential ID: `01M21K2M51FB5RQNQSKMJEYKHP`.
- Public audit note ID: `01M21K2M51P1FRAW1GTBJB4H3K`.
- Authentication through the stored local credential was verified against `/v1/me`.

The reviewed blowup publication is prepared in [publish-blowup-claims.py](../../scripts/publish-blowup-claims.py). It checks the unchanged approved payloads, Astra identity, Vasily co-maintainer and available quota before writes, then verifies public records and an unchanged replay. At restoration, Astra had used 3 of its 5 daily artifact slots, while the package needs 4. Publication therefore waits for the next UTC day; restoring access does not bypass participation quotas.
