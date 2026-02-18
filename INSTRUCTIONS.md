# Instructions

## Environment Setup

### Python Version

This project requires **Python 3.14**. The `.python-version` file pins this automatically for `uv`.

```bash
# Install Python 3.14 via uv (one-time)
uv python install 3.14

# Verify the active Python version
uv run python --version
```

### Dependencies

All dependencies are declared in `pyproject.toml` and locked in `uv.lock`.

```bash
# Install/sync all dependencies (creates .venv if needed)
uv sync

# Add a new dependency
uv add <package-name>

# Remove a dependency
uv remove <package-name>

# Update all dependencies to latest compatible versions
uv lock --upgrade && uv sync
```

### Virtual Environment

`uv sync` automatically creates and manages the `.venv` directory. You generally don't need to activate it manually since `uv run` handles that, but if you want a traditional shell session:

```bash
# Activate the venv
source .venv/bin/activate

# Deactivate when done
deactivate
```

## Running the Scraper

```bash
# Run via uv (preferred — uses the correct Python and venv automatically)
uv run python extrator_selenium.py

# Or, with the venv activated:
python extrator_selenium.py
```

### Configuring What to Extract

Edit lines 18–20 of `extrator_selenium.py`:

```python
classe = 'ADO'       # Case class: ADI, ADPF, ADO, ADC, RE, etc.
num_inicial = 1      # First case number
num_final = 200      # Last case number
```

To process a specific list of cases instead of a range, uncomment the `lista_processos` variable (line 24) and its corresponding loop (lines 183–185), and comment out the range loop (lines 188–191).

## Running the Dashboard

```bash
uv run streamlit run dashboard.py
```

This opens an interactive browser dashboard at `http://localhost:8501` for exploring the extracted STF data from `ArquivosConcatenados_1.csv`.

The sidebar provides global filters (class, status, year range, state). The main area has tabs for overview, temporal analysis, geographic distribution, justice workload, petitioner analysis, complexity metrics, and a searchable case explorer.

## Directory Structure

| Directory | Contents | Reprocessed? |
|---|---|---|
| `baixados/` | Completed/archived cases | Never |
| `temp/` | In-progress cases | Yes, on next run |
| `nao_encontrados/` | Cases that don't exist on STF | Never |

To force reprocessing of everything, delete all three directories.

## Common uv Commands

```bash
# Show installed packages and versions
uv pip list

# Run any command inside the managed venv
uv run <command>

# Show project dependency tree
uv tree

# Create a fresh venv from scratch (if something breaks)
rm -rf .venv && uv sync
```

## Troubleshooting

### ChromeDriver version mismatch

If Chrome was updated and the driver no longer matches:

```bash
# Check your Chrome version
google-chrome --version

# The dsd-br library's create_stf_webdriver() should handle driver
# management automatically. If it doesn't, install chromedriver manually
# or update dsd-br:
uv add --upgrade dsd-br
```

### CAPTCHA or 403 blocks

The STF portal may block requests. The scraper retries up to 5 times with exponential backoff (2s → 4s → 8s → 16s → 30s). If you keep getting blocked:

1. Increase the pause between batches (line 475 in `extrator_selenium.py`, currently 10s every 25 requests).
2. Wait a while before running again.
3. Check if the STF portal is up at https://portal.stf.jus.br/.

### Resuming after interruption

The scraper resumes automatically. Cases already saved in `baixados/` or `nao_encontrados/` are skipped. Cases in `temp/` are reprocessed to ensure fresh data.
