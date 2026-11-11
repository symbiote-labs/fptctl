# Signing in to a site

## Where credentials come from

fpt uses the first of these that applies:

1. `--profile NAME` on the command line;
2. environment variables: `FPT_SITE` with one of
   - `FPT_SCRIPT_NAME` and `FPT_API_KEY` (an API script),
   - `FPT_LOGIN` and `FPT_PASSWORD` (a user),
   - `FPT_SESSION_TOKEN` (a session);
3. the profile named by `FPT_PROFILE`;
4. the default profile.

`--site URL` overrides the site from any of these. `fpt auth status` prints the site, the auth
type, the identity and where the credentials came from (`source`), and fails with exit 3 if they
do not work.

## Profiles

```shell
fpt auth login --site https://studio.shotgrid.autodesk.com --script-name my_script
fpt auth login --name me --site https://studio.shotgrid.autodesk.com --login jane
fpt auth list
fpt auth use me
fpt auth logout me
```

- The secret (API key, password or session token) is read from a prompt on a terminal, or from
  stdin otherwise: `printf %s "$KEY" | fpt auth login --site ... --script-name ...`. It is stored
  in the OS keychain under the service `fpt`, keyed by profile name.
- The rest goes to `~/.config/fpt/config.toml` (or `$XDG_CONFIG_HOME/fpt/config.toml`, or the
  path in `FPT_CONFIG`).
- `auth login` checks the credentials against the site unless `--no-verify` is given.
- On a machine with no keychain backend, `auth login` exits 3 with "The system keychain is
  unavailable". Use the environment variables there; fpt has no plaintext secret store.

## Two-factor authentication

A user login on a site with 2FA needs a one-time code: `fpt auth login --login jane --otp 123456`.
The code is used once, and fpt stores the session it opens, not the password. When the session
expires, sign in again. Do not retry a failing user login in a loop: repeated failures can lock
the account.

## Acting as another user

With script credentials, `--sudo-as LOGIN` makes the request as that user, so their permissions
apply and `created_by`/`updated_by` show them.

## Proxies and certificates

- `--http-proxy [user:pass@]host[:port]` and `--ca-certs PATH` on `auth login` are stored with the
  profile. Note that the proxy string, including any password in it, is stored in plain text in
  the config file.
- With environment-variable credentials, `FPT_HTTP_PROXY` and `FPT_CA_CERTS` set them.

## Session tokens

`fpt auth token` prints a new session token for the current credentials. Each call opens a new
session. A token signs in through `FPT_SESSION_TOKEN` or `fpt auth login --session`.
