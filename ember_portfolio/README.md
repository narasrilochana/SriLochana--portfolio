# Sri Lochana: Retro Pixel Portfolio (FastAPI)

FastAPI + SQLite + HTML/CSS/JavaScript. Contact messages are saved in SQLite and emailed to you through Resend.

```
ember_portfolio/
├── main.py            FastAPI app: routes, Pydantic validation, error handlers
├── database.py        SQLite code (parameterised queries, auto-migration of `messages`)
├── emailer.py         Resend email: HTTPS API (default) or SMTP
├── settings.py        Loads secrets from a private .env file (no extra library)
├── requirements.txt   fastapi, uvicorn
├── render.yaml        Render deployment blueprint
├── .env.example       Template for your secrets (copy it, never commit the copy)
├── templates/index.html
├── static/ style.css, script.js, images/pixel-cat.png
└── tests/test_backend.py   offline tests for the database and email code
```

## 1. How the pieces work together

1. The browser loads `GET /` and FastAPI returns `templates/index.html`; CSS and JS come from `/static`.
2. A visitor fills in the form. `script.js` checks the fields, then calls `fetch("/api/contact", {method: "POST", body: JSON})`.
3. FastAPI hands the JSON to the `ContactForm` Pydantic model, which validates name, email and message. A bad field returns HTTP 422 with `{field: message}`.
4. The route checks the honeypot, a rate limit (5 per 10 minutes per visitor) and duplicate double-clicks.
5. `database.save_message()` inserts the row into SQLite using `?` placeholders.
6. `emailer.send_notification()` emails **your** `MAIL_TO` address, with the visitor's address as **Reply-To**. The body has name, email, full message and the IST timestamp.
7. The result is stored on the row (`email_status` = sent or failed) and returned as JSON. The page shows one status message and does not reload.

| Outcome | HTTP | What the visitor sees |
|---|---|---|
| Saved and emailed | 201 | Green "Your message has been sent" |
| Saved, email failed | 202 | Amber "saved, but the email alert could not be sent" |
| Bad input | 422 | Messages under the fields |
| Too many requests | 429 | Red message asking them to wait |
| Neither worked | 500 | Red "could not be sent" |

## 2. Hosting findings (checked against official sources, 15 Nov 2026)

**Outbound email on PythonAnywhere Free.** Free accounts can only reach an allowlist of sites over HTTP/HTTPS. Their forum staff say free accounts cannot use SMTP except Gmail's servers. So `smtp.resend.com` is not reachable from a free account. PythonAnywhere's allowlist page does list `api.resend.com`, so the **Resend HTTPS API** works on the free plan. That is why `EMAIL_METHOD=api` is the default. SMTP is still implemented (`EMAIL_METHOD=smtp`, port 465 SSL or 587 STARTTLS, user `resend`, password = API key) for any host with open outbound ports.

**FastAPI (ASGI) on PythonAnywhere.** Your old Flask WSGI instructions do **not** apply. PythonAnywhere's own help page calls ASGI support *experimental/beta*: sites are created through an API or the `pa` command-line tool (the web page for it is very limited unless support enables it for your account), static-file mappings are not supported, and the pricing is not settled. Third-party reviews conflict on whether free accounts can use it. **I could not confirm that your free account can host ASGI sites.** This project does not need static mappings, because FastAPI serves `/static` itself. To try PythonAnywhere, email support@pythonanywhere.com and ask them to enable ASGI sites for your free account (section 5).

**Recommended: Render (free).** Render runs FastAPI natively and your repo already had a `render.yaml`. Two limits to know about:
- Render Free **blocks SMTP ports 25, 465 and 587** (since 26 Sep 2025). The HTTPS API is unaffected, so email works.
- Render Free has an **ephemeral filesystem**. SQLite data is lost on every redeploy, restart or spin-down (idle for about 15 minutes). **The email notification becomes your permanent copy of each message.** If you need the database to persist for free, the next step is Render Postgres or another hosted database (a code change to `database.py`), or a paid plan with a disk.
- Free services sleep when idle, so the first visit after a quiet period is slow.

## 3. Resend setup (sender domain and the test sender)

1. Create an account at resend.com and add a domain you own (Domains, Add Domain).
2. Add the DNS records Resend shows (SPF and DKIM; a DMARC record is recommended) at your domain registrar and click Verify.
3. Choose a sender on that domain, e.g. `portfolio@yourdomain.com`, and set `MAIL_FROM`.
4. Create an API key (API Keys, "Sending access", restricted to your domain) and set `RESEND_API_KEY`.
5. Set `MAIL_TO` to your inbox.

**Test sender limits.** `onboarding@resend.dev` can only deliver to the email address of your own Resend account, so it is fine for a first test (set `MAIL_TO` to that address) but not for real use. Any other recipient is rejected until you verify your own domain. Without a verified domain the API returns an error like "domain is not verified", the visitor sees the amber "saved, email failed" message, and the row is marked `failed` in the database.

## 4. Run locally

```bash
cd ember_portfolio
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # then edit .env with your values
uvicorn main:app --reload
```
Open http://127.0.0.1:8000. API docs are at `/docs`. Offline tests: `python tests/test_backend.py`.

## 5. Deploy

### Option A: Render (recommended)
1. Commit and push `SriLochana-portfolio` to GitHub (the real `.env` is git-ignored).
2. Render dashboard: New, Blueprint, pick the repo. It reads `ember_portfolio/render.yaml` (`rootDir: ember_portfolio`; if your `render.yaml` sits in `ember_portfolio/`, move it to the repo root or create a Web Service manually with root directory `ember_portfolio`).
3. Enter `RESEND_API_KEY`, `MAIL_FROM`, `MAIL_TO` when asked. `ADMIN_TOKEN` is generated for you.
4. After the deploy, open `https://<your-service>.onrender.com/health`. It should show `"email_configured": true`.

### Option B: PythonAnywhere (only if support enables ASGI for your account)
Do these in a Bash console. Check things before trusting them:
```bash
cd /home/Lochana07/SriLochana-portfolio && git pull
ls ~/.virtualenvs 2>/dev/null          # see whether an old virtualenv exists
ls /usr/bin/python3*                   # see which Python versions are installed
# Make a fresh virtualenv instead of reusing an old one (pick a version from the list above):
mkvirtualenv --python=/usr/bin/python3.12 fast_venv
pip install -r /home/Lochana07/SriLochana-portfolio/ember_portfolio/requirements.txt
python -c "import fastapi, uvicorn; print(fastapi.__version__, uvicorn.__version__)"   # must print versions
```
Secrets: create `/home/Lochana07/.portfolio.env` (outside the repo) from `.env.example`, then `chmod 600 ~/.portfolio.env`. `settings.py` finds it automatically.

The site command PythonAnywhere runs (from their ASGI help page) has this shape. Follow their current page for exact steps, because the interface is beta and may change:
```
/home/Lochana07/.virtualenvs/fast_venv/bin/uvicorn --uds ${DOMAIN_SOCKET} main:app --app-dir /home/Lochana07/SriLochana-portfolio/ember_portfolio
```
There is **no WSGI file** and no static-file mapping to configure. To update later: `git pull`, then reload the site from PythonAnywhere (or through their API).

## 6. Replace your old Flask project safely
1. Back up first: `cp ember_portfolio/portfolio.db ~/portfolio.db.backup`.
2. `git checkout -b fastapi-version`.
3. Replace `templates/index.html`, `static/style.css`, `static/script.js`, `static/images/pixel-cat.png` and `requirements.txt` with the new files. Add `main.py`, `database.py`, `emailer.py`, `settings.py`, `.env.example`, `.gitignore`, `tests/`, and replace `render.yaml`.
4. Delete `app.py`. Keep your existing `portfolio.db`. On start, `init_db()` keeps your `messages` rows and only adds the missing columns (`created_at`, `email_status`, `email_error`).
5. Run the tests and the local check, then merge and deploy.

## 7. Deployment testing checklist
- [ ] `/health` returns `status: ok`, `database: true`, `email_configured: true`
- [ ] Home page loads with the cat image and styles (no 404s in the browser console)
- [ ] All nav links scroll to their sections; the Menu button works on a phone width
- [ ] Each "Learn more" button opens its dialog and Close works
- [ ] Submitting an empty form shows field errors and sends nothing
- [ ] A valid message shows one green confirmation and clears the form
- [ ] The email arrives in **your** inbox, shows name, email, message and time, and Reply goes to the visitor
- [ ] `GET /api/messages` with header `X-Admin-Token` lists the row with `email_status: sent`
- [ ] Temporarily break `RESEND_API_KEY`: you get the amber message and the row says `failed`
- [ ] Rapid double-click sends only one email

## 8. Viva preparation
- **HTML/CSS/JS** build the page. CSS variables hold the palette; the layout uses grid and flexbox; JavaScript handles the menu, dialogs and `fetch()`.
- **FastAPI** is a Python web framework. Routes are decorated functions; it generates `/docs` automatically. **Uvicorn** is the ASGI server that runs it. Flask is WSGI and works differently, which is why deployment changed.
- **Pydantic** defines the `ContactForm` model and its validators; invalid data is rejected before the route runs (HTTP 422).
- **SQLite** is a file database; `sqlite3` is built into Python. `?` placeholders (parameterised queries) stop SQL injection.
- **Resend** is an email service. Its HTTPS API is a POST with a bearer key; its SMTP server is `smtp.resend.com`. The free PythonAnywhere plan only allows allow-listed HTTPS, so the API is used.
- **Reply-To** is the header that makes "Reply" go to the visitor while the email still goes to me.
- **Security:** secrets in environment variables, never in GitHub; honeypot, rate limit, length limits; HTML-escaped email body; CR/LF stripped from header values.
- **Why `def` routes?** `sqlite3` and `urllib` block. FastAPI runs plain `def` routes in a thread pool, so the server stays responsive.
- **Limitations to state honestly:** Render Free loses SQLite data on restart; PythonAnywhere ASGI is beta.
