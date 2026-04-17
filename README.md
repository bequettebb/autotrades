# Streamlit Paper Dashboard

This small app shows the bot's paper-trading results using either:

- a public JSON URL set with `BOT_STATUS_JSON_URL`
- a bundled `cloud/status.json` file for Streamlit Cloud fallback
- local `reports/status.json`
- an uploaded `status.json` file from the sidebar

## Run locally

From the main project:

```bash
pip install -r streamlit_dashboard_app/requirements.txt
streamlit run streamlit_dashboard_app/app.py
```

Or use the included local launcher:

```bash
zsh streamlit_dashboard_app/run_local_dashboard.sh
```

## Use with uploaded JSON

If you host this app on Streamlit Community Cloud, upload `reports/status.json` from your bot machine in the sidebar.

## Streamlit Cloud

For Streamlit Cloud, this app can render directly from the repo copy at:

```text
streamlit_dashboard_app/cloud/status.json
```

The project root includes a GitHub Actions workflow that can refresh that file automatically:

```text
.github/workflows/publish-streamlit-snapshot.yml
```

Add your Finnhub key in GitHub:

1. Repo `Settings`
2. `Secrets and variables`
3. `Actions`
4. Create `FINNHUB_API_KEY`

Then run the workflow manually or let the schedule update the bundled snapshot for Streamlit Cloud.
The workflow runs `python main.py --once` and publishes the generated `reports/status.json`.

## Important

If the app is hosted on Streamlit Cloud, it cannot directly access files on your Mac or your local `127.0.0.1` dashboard API.

To make Streamlit Cloud work without manual upload, use one of these:

1. Set `BOT_STATUS_JSON_URL` to a public JSON file URL.
2. Keep `streamlit_dashboard_app/cloud/status.json` updated in the deployed repo.

The sidebar includes a source selector so you can explicitly choose Auto, Uploaded JSON, Public URL, API, Local reports snapshot, or the bundled cloud snapshot.

To refresh the bundled cloud snapshot from your latest local bot result:

```bash
zsh scripts/publish_streamlit_snapshot.sh
```

## Optional local reports path

If your reports folder lives somewhere else:

```bash
BOT_REPORTS_DIR=/path/to/reports streamlit run streamlit_dashboard_app/app.py
```
