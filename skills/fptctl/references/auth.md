# Signing in to a site

## Where credentials come from

fptctl uses the first of these that applies:

1. `--profile NAME` on the command line;
2. environment variables: `FPTCTL_SITE` with one of
   - `FPTCTL_SCRIPT_NAME` and `FPTCTL_API_KEY` (an API script),
   - `FPTCTL_LOGIN` and `FPTCTL_PASSWORD` (a user),
   - `FPTCTL_SESSION_TOKEN` (a session);
3. the profile named by `FPTCTL_PROFILE`;
4. the default profile.

`--site URL` overrides the site from any of these. `fptctl auth status` prints the site, the auth
type, the identity and where the credentials came from (`source`), and fails with exit 3 if they
do not work.

## Profiles

```shell
fptctl auth login --site https://studio.shotgrid.autodesk.com --script-name my_script
fptctl auth login --name me --site https://studio.shotgrid.autodesk.com --login jane
fptctl auth list
fptctl auth use me
fptctl auth logout me
```

- The secret (API key, password or session token) is read from a prompt on a terminal, or from
  stdin otherwise: `printf %s "$KEY" | fptctl auth login --site ... --script-name ...`. It is stored
  in the OS keychain under the service `fptctl`, keyed by profile name.
- The rest goes to `~/.config/fptctl/config.toml` (or `$XDG_CONFIG_HOME/fptctl/config.toml`, or the
  path in `FPTCTL_CONFIG`).
- `auth login` checks the credentials against the site unless `--no-verify` is given.
- On a machine with no keychain backend, `auth login` exits 3 with "The system keychain is
  unavailable". Use the environment variables there; fptctl has no plaintext secret store.

## Two-factor authentication

A user login on a site with 2FA needs a one-time code: `fptctl auth login --login jane --otp 123456`.
The code is used once, and fptctl stores the session it opens, not the password. When the session
expires, sign in again. Do not retry a failing user login in a loop: repeated failures can lock
the account.

## Acting as another user

With script credentials, `--sudo-as LOGIN` makes the request as that user, so their permissions
apply and `created_by`/`updated_by` show them.

## Proxies and certificates

- `--http-proxy [user:pass@]host[:port]` and `--ca-certs PATH` on `auth login` are stored with the
  profile. Note that the proxy string, including any password in it, is stored in plain text in
  the config file.
- With environment-variable credentials, `FPTCTL_HTTP_PROXY` and `FPTCTL_CA_CERTS` set them.

## Session tokens

`fptctl auth token` prints a new session token for the current credentials. Each call opens a new
session. A token signs in through `FPTCTL_SESSION_TOKEN` or `fptctl auth login --session`.
