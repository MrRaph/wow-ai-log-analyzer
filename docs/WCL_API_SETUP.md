# Obtaining Warcraft Logs API v2 credentials

The app uses the WCL API v2 (GraphQL) in two ways:

- **Server-side (client_credentials)** — public data only (top logs, public
  reports). The whole instance shares one client.
- **Per-user (authorization_code)** — optional. When a user clicks
  *Connect Warcraft Logs* on their profile, their token is used so the
  analyzer can read **their private and unlisted reports**.

Both flows use the *same* WCL API client. You only register one.

## Steps

1. Go to https://www.warcraftlogs.com/ and sign in.
2. Open https://www.warcraftlogs.com/api/clients/.
3. Click **Create Client**.
4. Fill in:
   - **Application Name:** anything, e.g. `wow-ai-log-analyzer`.
   - **Redirect URLs (comma-separated):** the URLs WCL is allowed to redirect
     the browser to after a user authorises. Use both your prod and dev URLs:
     ```
     https://<your-domain>/api/v1/auth/wcl/callback, http://localhost:8000/api/v1/auth/wcl/callback
     ```
     The URL match is exact — including scheme, host, port and path.
   - **Public Client:** **leave UNCHECKED**. Both flows exchange the auth
     code for a token server-side, which only works for a confidential client.
5. Save. You will see a **Client ID** and a **Client Secret**.
6. Copy them into your `.env`:
   ```env
   WCL_CLIENT_ID=...
   WCL_CLIENT_SECRET=...
   WCL_REDIRECT_URI=https://<your-domain>/api/v1/auth/wcl/callback
   ```
   Set `WCL_REDIRECT_URI` to the **exact** URL the browser will land on. For
   local dev that's `http://localhost:8000/api/v1/auth/wcl/callback`.

## Classic Fresh (optional)

Classic Fresh uses a separate Warcraft Logs host (`fresh.warcraftlogs.com`) and
its own OAuth client registry. This is **separate** from retail and requires its
own credentials.

### 1. Register a Fresh OAuth client

1. Go to https://fresh.warcraftlogs.com/ and sign in.
2. Open https://fresh.warcraftlogs.com/api/clients/.
3. Click **Create Client** and fill in the same way as the retail client, using
   the Fresh redirect URLs:
   ```
   https://<your-domain>/api/v1/auth/wcl-fresh/callback, http://localhost:8000/api/v1/auth/wcl-fresh/callback
   ```
4. Copy the credentials to `.env`:
   ```env
   WCL_FRESH_CLIENT_ID=...
   WCL_FRESH_CLIENT_SECRET=...
   WCL_FRESH_REDIRECT_URI=https://<your-domain>/api/v1/auth/wcl-fresh/callback
   ```

### 2. Enable Fresh top-logs

Fresh top-logs (public leaderboards, weekly cron, admin seeding) are gated by
a separate feature flag. Once credentials are set, also add:

```env
TOP_LOGS_FRESH_ENABLED=true
```

When `false` (default), the API returns empty lists for Fresh top-log requests
and the weekly cron only seeds retail encounters.

### Classic Era vs Classic Fresh

| Feature | Classic Era (`classic.warcraftlogs.com`) | Classic Fresh (`fresh.warcraftlogs.com`) |
|---|---|---|
| OAuth registry | Shares **retail** credentials | Requires **separate** Fresh credentials |
| API host | `www.warcraftlogs.com` | `fresh.warcraftlogs.com` |
| Top-logs flag | No separate flag (retail flag) | `TOP_LOGS_FRESH_ENABLED` |
| URL import | Automatic — detected from URL subdomain | Automatic — detected from URL subdomain |

## Rate limiting

WCL applies a per-client request budget (rolling window). The analyzer keeps
its own cache — top logs are refreshed weekly (`TOP_LOGS_CRON`, default
Wednesday 08:00 UTC, ~1-3 h after the EU weekly reset) and individual reports
are cached after the first fetch — so the budget is rarely a concern. If you
see 429s in the worker logs you can lower `TOP_LOGS_LIMIT` or
`TOP_LOGS_DETAIL_COUNT` in `.env`.

## Privacy

- Without *Connect Warcraft Logs*: only **public** reports are visible.
- After *Connect Warcraft Logs*: the analyzer can read whatever reports the
  signed-in user can see on warcraftlogs.com (own private/unlisted reports +
  guild reports they are part of).
- Stored tokens are encrypted at rest with a key derived from `SECRET_KEY`
  (Fernet/AES-128-CBC + HMAC). Rotating `SECRET_KEY` invalidates all stored
  tokens — users will be asked to reconnect.
- Users can revoke at any time via *Profile → Disconnect Warcraft Logs*.
