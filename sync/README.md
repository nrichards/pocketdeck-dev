# pocketdeck-sync

Watch a local directory of Pocket Deck Python apps. When a `.py` file changes,
push it to the deck over SCP and trigger `r <module>` over SSH so MicroPython
reloads it.

## One-time setup

### On your Mac

Install `fswatch` (BSD `fswatch`, not the Linux one):

```bash
brew install fswatch
```

Generate an SSH key if you don't already have one dedicated to the deck:

```bash
ssh-keygen -t rsa -m PEM -f ~/.ssh/pocketdeck_id_rsa
```

Note the `-m PEM`. The Pocket Deck SSH client documentation calls out PEM
format explicitly.

### On the deck

According to `docs/ssh_scp_readme.md`, key-based auth on the deck works by
placing the **private** key at `/config/ssh/id_rsa` on the deck — the deck is
acting as the SSH/SCP **client** when you run `scp` or `ssh` from it. For the
direction we want (Mac pushing files to the deck), the deck is the server, and
you authenticate with a password using `scp -p`.

So the simpler path is password auth from the Mac side. Put the password in a
local config file (gitignored), load it into an env var, and let `sshpass`
feed it to `scp` and `ssh`.

```bash
brew install hudochenkov/sshpass/sshpass
```

Start configuring the sync environment with this example file:

```bash
cp pocketdeck-dev/sync/pocketdeck.env.example ~/.pocketdeck.env
```

Then edit `~/.pocketdeck.env` with your connection info:

```bash
# ~/.pocketdeck.env  (chmod 600)
export POCKETDECK_HOST=192.168.1.42
export POCKETDECK_USER=user
export POCKETDECK_PASSWORD=yourpassword
export POCKETDECK_REMOTE_DIR=/sd/py
```

and ensure it's accessible to only the current user:

```bash
chmod 600 ~/.pocketdeck.env
```

Get the host from running `wifi` on the deck. The user/password pair is
whatever the deck's SSH server is configured to accept. (The deck uses
`/config/netserver_password` for the netserver; SSH credentials are separate —
check your deck's config.)

## Usage

Start the watcher pointing at your local app directory, e.g. `~/code/pocketdeck-apps`:

```bash
./watch.sh ~/code/pocketdeck-apps
```

Edit any `.py` file in that tree. Each save will:

1. SCP the file to `$POCKETDECK_REMOTE_DIR` on the deck.
2. SSH in and run `r <module_name>` to reload and execute it.

One-shot push without the watcher:

```bash
./push.sh ~/code/pocketdeck-apps/my_app.py
```

One-shot push + run:

```bash
./run.sh ~/code/pocketdeck-apps/my_app.py
```

## Notes and limitations

- `r` executes the module in the **current** command-shell screen. Make sure a
  shell is focused on a screen you want output to land on (usually screen 2).
- If your app uses sub-modules, edit-save-sync only pushes the one file that
  changed. Use `push_all.sh` after structural changes.
- The deck's SSH server handling and shell environment is simple — don't
  expect fancy features like job control. These scripts keep it to single
  commands per connection.
- Network hiccups will cause the occasional failed push. The scripts log and
  continue rather than exiting — you'll see the error and your next save will
  retry.
