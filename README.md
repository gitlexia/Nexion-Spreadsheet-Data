# Nexion Social Reporting

A small internal web app that generates Nexion Facebook and Google reporting spreadsheets from a permanently stored facility list.

## What the exports contain

**Facebook Excel**
- State
- Facility
- Facebook Likes
- Facebook Followers
- Facebook Posts (Target Month)

**Google Excel**
- State
- Facility
- Google Rating
- Google Review Count

Addresses are stored only so Google can identify the correct facility. They are **not exported**.

## Run locally

1. Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the environment template:

```bash
cp .env.example .env
```

4. Export the values in `.env` into your shell, or use your preferred environment loader. For a quick Mac/Linux test:

```bash
set -a
source .env
set +a
```

5. Start the app:

```bash
uvicorn main:app --reload
```

6. Open:

```text
http://127.0.0.1:8000
```

## Facility list

The permanent facility list lives at:

```text
data/facilities.json
```

It was seeded from `facilities_full.xlsx` and currently contains 57 active facilities.

The app keeps the address/city/ZIP internally for Google matching, but exports only State + Facility + metrics.

Optional fields already exist for each facility:

```json
{
  "google_place_id": null,
  "facebook_page_id": null
}
```

If you fill those IDs in later, the app can skip name matching and target the exact listing/page.

## GitHub vs hosting

Put this whole project in a GitHub repository, but **do not use GitHub Pages for the deployed app**. GitHub Pages only serves static frontend files. This app needs Python plus secret Google/Meta credentials on the server.

The simplest deployment is:

1. Push this folder to GitHub.
2. Create a Render web service from the repo.
3. Render will read `render.yaml`.
4. Add the four environment variables in Render's dashboard.
5. Deploy.

Your API keys stay on the server and never appear in the browser or GitHub repository.

## Important production note

The current job queue and generated report files live in the app process/filesystem. That is intentionally simple for v1. For a more durable production version, move job state/files to a database/object store.

Also, Meta access tokens expire depending on how they are issued. For a long-running company tool, use the access-token approach your Meta Business setup officially supports rather than committing a token to code.
