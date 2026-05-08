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
   - **Public Client:** **leave UNCHECKED**. Both flows tauschen den Code
     server-seitig gegen ein Token, das geht nur als confidential client.
5. Save. You will see a **Client ID** and a **Client Secret**.
6. Copy them into your `.env`:
   ```env
   WCL_CLIENT_ID=...
   WCL_CLIENT_SECRET=...
   WCL_REDIRECT_URI=https://<your-domain>/api/v1/auth/wcl/callback
   ```
   Set `WCL_REDIRECT_URI` to the **exact** URL the browser will land on. For
   local dev that's `http://localhost:8000/api/v1/auth/wcl/callback`.

## Rate limiting

WCL applies a per-client request budget (rolling window). The analyzer keeps
its own cache (top logs once per day, individual reports cached after first
fetch) so the budget is rarely a concern. If you see 429s in the worker logs
you can lower `TOP_LOGS_LIMIT` in `.env`.

## Privacy

- Without *Connect Warcraft Logs*: only **public** reports are visible.
- After *Connect Warcraft Logs*: the analyzer can read whatever reports the
  signed-in user can see on warcraftlogs.com (own private/unlisted reports +
  guild reports they are part of).
- Stored tokens are encrypted at rest with a key derived from `SECRET_KEY`
  (Fernet/AES-128-CBC + HMAC). Rotating `SECRET_KEY` invalidates all stored
  tokens — users will be asked to reconnect.
- Users can revoke at any time via *Profile → Disconnect Warcraft Logs*.
