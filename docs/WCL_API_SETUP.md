# Obtaining Warcraft Logs API v2 credentials

The app uses the public WCL API v2 (GraphQL) with OAuth2 client credentials.

## Steps

1. Go to https://www.warcraftlogs.com/ and sign in.
2. Open https://www.warcraftlogs.com/api/clients/.
3. Click **Create Client**.
4. Fill in:
   - **Application Name:** anything, e.g. `wow-ai-log-analyzer`
   - **Redirect URLs:** `http://localhost` (the analyzer uses the
     client-credentials flow, so this is unused — but the field is required)
   - **Public Client:** leave **unchecked** (we want a confidential client to
     use the client-credentials grant). If you have to use a public client,
     you can still proceed — only the user-authenticated flows will be
     unavailable.
5. Save. You will see a **Client ID** and a **Client Secret**.
6. Copy them into your `.env`:
   ```env
   WCL_CLIENT_ID=...
   WCL_CLIENT_SECRET=...
   ```

## Rate limiting

WCL applies a per-client request budget (rolling window). The analyzer keeps
its own cache (top logs are fetched once per day, individual reports are
cached after first fetch) so the budget is rarely a concern, but if you see
429s in the worker logs you can lower `TOP_LOGS_LIMIT` in `.env`.

## Privacy

The OAuth client-credentials grant gives the analyzer **public** access only —
you cannot view private/unlisted logs without a user-authorization flow, which
is intentionally not implemented. Users must mark their reports public on WCL
before pasting them into the analyzer.
