# Steel & Stud Leads Dashboard — Private Live Site

A password-protected, live-updated leads dashboard for steelandstud.com, hosted on GitHub Pages.

## How the protection works

The dashboard contains real customer contact details, so the published `index.html` does **not** carry the data in plaintext. Instead:

1. The master file `Steel-Stud-Leads-Dashboard.html` (refreshed daily by Cowork) holds the full plaintext data and stays **only on your local machine** — it is gitignored.
2. `build.py` reads the master + the password from `config.local.txt` and produces `index.html` with the data encrypted using **AES-GCM 256** and a key derived from the password via **PBKDF2-SHA256 with 300,000 iterations** and a fresh random salt.
3. Visitors of the published URL see a login screen. When they enter the password, decryption happens entirely in their browser via the Web Crypto API; nothing about the password leaves their device.
4. Brute-forcing the password is computationally expensive (PBKDF2 makes each guess ~300k SHA-256 rounds), so a strong shared password is sufficient protection for a small team.

> **Strength of this scheme:** good enough for a 1–3-person team with a strong password. Not equivalent to authenticated cloud hosting. Anyone who learns the password can decrypt the dashboard. Rotate it occasionally.

## Folder contents

| File | Purpose | Committed? |
| --- | --- | --- |
| `Steel-Stud-Leads-Dashboard.html` | Master HTML, plaintext data, refreshed daily | **No** (gitignored) |
| `index.html` | Encrypted dashboard for GitHub Pages | Yes |
| `build.py` | Build script that produces `index.html` | Yes |
| `config.local.txt` | Shared password | **No** (gitignored) |
| `config.sample.txt` | Template for the password file | Yes |
| `.github/workflows/deploy.yml` | Auto-deploys `index.html` to Pages on push | Yes |
| `.gitignore` | Keeps secrets and the master file out of git | Yes |

## First-time setup

You need a GitHub account, Git installed on Windows, and Python 3 with the `cryptography` library.

### 1. Create the GitHub account (do this yourself in your browser)

- Go to <https://github.com/signup> and create your account if you don't already have one.
- Verify your email.

### 2. Install required tools (one-time)

In a Windows PowerShell or Command Prompt:

```powershell
# Confirm git is installed
git --version

# Install the cryptography library used by build.py
python -m pip install cryptography
```

If `git --version` fails, install Git from <https://git-scm.com/download/win>.

### 3. Clean up sandbox artefacts and prepare the folder

Cowork's sandbox left a broken `.git` directory in the folder. Delete it before re-initialising:

```powershell
cd "$env:USERPROFILE\Documents\Claude\Artifacts\steelandstud-leads-dashboard"
Remove-Item -Recurse -Force .git -ErrorAction SilentlyContinue
```

### 4. Pick your real password

Open `config.local.txt` in Notepad and replace the auto-generated password with something memorable but strong (16+ characters, mixed case, numbers, symbols). Then rebuild:

```powershell
python build.py
```

You should see `Built index.html  records encrypted: 23  PBKDF2 iterations: 300,000`.

### 5. Create the private repo on GitHub

In your browser at <https://github.com/new>:

- **Repository name:** `steelandstud-leads-dashboard` (or any name you like)
- **Visibility:** **Public** is fine — the data is encrypted. Private also works.
- Do **not** add a README, .gitignore, or license (the local folder already has them).
- Click **Create repository**.

GitHub will show a "quick setup" page with a URL like `https://github.com/<your-username>/steelandstud-leads-dashboard.git`. Note it.

### 6. Initialise git locally and push

Back in PowerShell, in the dashboard folder:

```powershell
git init -b main
git add .
git commit -m "Initial encrypted dashboard"
git remote add origin https://github.com/<your-username>/steelandstud-leads-dashboard.git
git push -u origin main
```

The first push will pop a Windows credential window — sign in with your GitHub account and the credential is cached for future pushes.

### 7. Enable GitHub Pages

In the repo on GitHub:

- **Settings → Pages**
- **Source:** "GitHub Actions"

GitHub will use `.github/workflows/deploy.yml` (already in your repo) to deploy.

Within a minute, **Actions** tab → the latest "Deploy to GitHub Pages" run will finish and your live URL will be:

```
https://<your-username>.github.io/steelandstud-leads-dashboard/
```

### 8. Share with teammates

Send each teammate two things:

- The live URL
- The password from `config.local.txt`

They open the URL, enter any user ID (just for display) and the password, and the dashboard decrypts in their browser. **Do not send the password over the same channel as the URL.**

## Daily refresh

The Cowork scheduled task `steelandstud-daily-leads-report` updates `Steel-Stud-Leads-Dashboard.html` every morning. To push the refresh to the live site, you currently need to run two commands after each refresh:

```powershell
cd "$env:USERPROFILE\Documents\Claude\Artifacts\steelandstud-leads-dashboard"
python build.py
git add index.html
git commit -m "Daily refresh"
git push
```

### Optional: automate the push

To have the scheduled task do this automatically, append the following block to the task definition's STEP 7 (or add a new STEP 8). Open the task in Cowork → edit → add at the end:

```
STEP 8 — Publish to GitHub Pages
- After the dashboard is rebuilt, run the publish script:
  - cd C:\Users\dell\Documents\Claude\Artifacts\steelandstud-leads-dashboard
  - python build.py
  - git add index.html
  - git diff --quiet --cached || git commit -m "Daily refresh $(date +%Y-%m-%d)"
  - git push
- If the push fails (network or auth), report the error in the chat summary and continue.
```

This relies on your git credentials already being cached from step 6.

## Rotating the password

1. Edit `config.local.txt` with the new password.
2. `python build.py`
3. `git add index.html && git commit -m "Rotate password" && git push`
4. Share the new password with teammates over a different channel.

The old `index.html` in git history still uses the old password, so if you need to be thorough, `git filter-repo` or a force-push of a squashed history will scrub it.

## Troubleshooting

**`build.py` says `cryptography` is missing.**
`python -m pip install cryptography`

**Pages workflow fails with "Pages source not configured".**
Make sure **Settings → Pages → Source** is set to **GitHub Actions** (not "Deploy from a branch").

**Teammate sees "Wrong user ID or password".**
Re-share the password — it's case-sensitive and copy/paste sometimes adds invisible whitespace. The "User ID" field is for display only and accepts anything.

**The dashboard loads but charts are blank.**
GitHub Pages serves over HTTPS; the Chart.js CDN tag in the dashboard uses HTTPS already, so this should not happen. If it does, your network or extension is blocking jsdelivr.net.

**You committed `config.local.txt` or `Steel-Stud-Leads-Dashboard.html` by accident.**
The encrypted scheme breaks the moment plaintext lands in git. Rotate the password immediately, force-push a history that excludes those files (use `git filter-repo` or [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/)), and rebuild.
