# 📊 Tableau Connector

**Turn messy CSV/Excel files into Tableau-ready data with auto-generated insights.**

Drop in a spreadsheet → get a cleaned Tableau extract, a categorized list of data stories, and a polished HTML report. No coding required.

```
your_data.csv  →  profile · cleanse · narrate · export  →  Tableau Desktop
```

---

## What it does

1. **Profiles** your data — detects types, missing values, duplicates, outliers
2. **Cleanses** it — fills gaps, removes duplicates, fixes types (every fix is logged)
3. **Finds insights** — trends, correlations, segments, anomalies, distributions
4. **Narrates with Claude** — turns raw numbers into plain-English **data stories**, grouped into 8 categories:

   | Category | What it captures | Suggested Tableau viz |
   |---|---|---|
   | Trends | Time-series direction, seasonality | Line chart |
   | Anomalies | Outliers, spikes, drops | Highlight table |
   | Distributions | Skew, concentration, gaps | Histogram, box plot |
   | Relationships | Correlations between fields | Scatter, heatmap |
   | Segments | Group differences | Grouped bar, treemap |
   | Comparisons | Top-N, share of total | Bar chart |
   | Composition | Part-to-whole mix | Stacked bar, pie |
   | Data Quality | Missingness, type issues | Profile table |

5. **Exports** a Tableau-ready `.hyper` extract, a cleaned CSV, and an HTML report

---

## Setup (one time, ~3 minutes)

### macOS / Linux

1. Open **Terminal** (Cmd+Space → "Terminal" on Mac)
2. `cd` into this project folder
3. Run the installer:
   ```bash
   ./install.sh
   ```

When it finishes, you'll have a file named **`Tableau Connector.command`** in this folder.

### Windows

1. Open **File Explorer** and navigate to this project folder
2. **Double-click `install.bat`**
3. Wait for it to finish (a console window will appear — that's normal)

When it finishes, you'll have a file named **`Tableau Connector.bat`** in this folder.

### Requirements

- **Python 3.10 or newer** — get it from [python.org/downloads](https://python.org/downloads). On Windows, tick the *"Add Python to PATH"* box during install.
- An internet connection for the one-time dependency download
- An **Anthropic API key** (see next section)

---

## Get an Anthropic API key (BYOK)

The connector uses Claude to write your data stories. You need your own API key.

1. Go to **[console.anthropic.com](https://console.anthropic.com)** and sign up (free).
2. Once signed in, go to **Settings → API keys**.
3. Click **Create Key**, give it a name (e.g. "Tableau Connector"), and copy the key.
4. The key starts with `sk-ant-...` — keep it secret.

**Cost:** a typical run costs about **$0.01 – $0.05** in API credits. Anthropic gives new accounts a small free credit balance — plenty for testing.

In the app, paste the key into the **API key** field. Toggle **"Save key to `.env`"** so you don't have to paste it again next time.

> The app has a **"🔗 Don't have a key?"** button that opens the right page for you.

---

## Run it

### macOS / Linux

**Double-click `Tableau Connector.command`** in this folder.

### Windows

**Double-click `Tableau Connector.bat`** in this folder.

You'll see a full-screen interface like this:

```
┌──────────────────────────────────────────────────────────────────┐
│           📊  T A B L E A U   C O N N E C T O R                 │
├─────────────────────────────────────┬───────────────────────────┤
│ 📂 Source                           │ ⚡ Pipeline               │
│   [samples/student_grades.csv  ]    │   ① INGEST                │
│   ✓ CSV · 2.8KB                     │   ② PROFILE               │
│                                     │   ③ CLEANSE               │
│ 🔑 Anthropic credentials (BYOK)     │   ④ INSIGHTS              │
│   [sk-ant-•••••••••••• ]            │   ⑤ NARRATE  (Claude)     │
│   ✓ sk-ant-…aB9X                    │   ⑥ EXPORT                │
│   [ 🔗 Don't have a key? ]          │                           │
│   Model: [claude-sonnet-4-6  ]      │ 📦 Output bundle          │
│   [○] Save key to .env              │   report.html             │
│                                     │   cleaned.hyper           │
│ ⚙ Options                           │   cleaned.csv             │
│   Cleanse: [Auto-clean    ▼]        │   insights.json           │
│                                     │   ...                     │
└─────────────────────────────────────┴───────────────────────────┘
            [ Help (F1) ]  [ Quit ]  [ ▶ Run pipeline ]
```

### Steps

1. **Pick your file** — type or paste the path, or drop your CSV/Excel into the `samples/` folder so it's pre-filled
2. **Paste your API key** (one time — toggle "Save to .env" to remember)
3. Click **▶ Run pipeline** (or press **Ctrl+R**)

The next screen shows live progress. When it finishes, you'll see a category breakdown and a button to **📂 Open report**.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+R` | Run the pipeline |
| `F1` | Open help |
| `Ctrl+Q` | Quit |
| `Tab` | Move between fields |
| `o` (on results screen) | Open `report.html` in your browser |
| `n` (on results screen) | Run another file |

---

## Output

Every run creates a timestamped folder inside `outputs/`. For example:

```
outputs/student_grades_20260513_142301/
├── report.html           ← Pretty HTML report — open this first
├── cleaned.hyper         ← Drag into Tableau Desktop
├── cleaned.csv           ← Same data as CSV (portable)
├── insights.json         ← Machine-readable findings
├── cleanse_audit.json    ← Every cleansing decision, with reasoning
└── run.log               ← Step-by-step log
```

### Using the output in Tableau

**Easiest:** Open Tableau Desktop → File → Open → pick `cleaned.hyper`. Your data is already typed and cleaned.

**If `.hyper` didn't generate** (some systems can't run the Hyper API): open `cleaned.csv` in Tableau instead.

---

## Troubleshooting

<details>
<summary><strong>"Python not found" during install</strong></summary>

Install Python from [python.org/downloads](https://python.org/downloads). On Windows, make sure to tick **"Add Python to PATH"** during the installer.

After installing, **close and reopen** the terminal / Command Prompt before running `./install.sh` or `install.bat` again.
</details>

<details>
<summary><strong>"Hyper API unavailable"</strong></summary>

The `.hyper` file step is skipped, but **`cleaned.csv` is still created**. Open the CSV in Tableau instead — same data, just a less optimized format.

This usually happens on very new Python versions where Tableau's Hyper library hasn't shipped a wheel yet. Try Python 3.11 or 3.12 if you want `.hyper` support.
</details>

<details>
<summary><strong>"LLM error" or API failures</strong></summary>

- **Bad API key**: check that it starts with `sk-ant-` and doesn't have extra spaces.
- **Out of credit**: log into [console.anthropic.com](https://console.anthropic.com) and check your balance.
- **No internet**: the app needs to reach Anthropic's servers.
</details>

<details>
<summary><strong>"File not found" when I pick my CSV</strong></summary>

Paths are relative to wherever you launched the app. The simplest fix: drop your file into the `samples/` folder and pick it from there.

Or use an absolute path like `/Users/yourname/Desktop/data.csv` (Mac) or `C:\Users\yourname\Desktop\data.csv` (Windows).
</details>

<details>
<summary><strong>The launcher closes immediately on Windows</strong></summary>

That means an error happened. Right-click `Tableau Connector.bat` → **Edit**, you'll see what went wrong. Common causes:

- Python wasn't installed with "Add to PATH"
- The `.venv` folder was deleted — re-run `install.bat`
</details>

---

## For developers

The CLI (no TUI) is also available after install:

```bash
.venv/bin/connector run samples/student_grades.csv
```

Project layout:

```
src/
  cli.py       Typer-based CLI entry point
  tui.py       Textual-based interactive UI
  ingest.py    CSV/Excel loading
  profile.py   Type detection, stats, correlations
  cleanse.py   Configurable cleansing with full audit
  insights.py  Raw finding generation
  narrate.py   Claude API integration (BYOK)
  export.py    .hyper / CSV / JSON / HTML output
  logger.py    Rich console + run.log + cleanse audit
```
