# File Upload Guide

**Who is this for?** Anyone who needs to load data files into CIS Trade Hive — operations staff, data teams, or business users uploading position or price data.

---

## What Can I Upload?

The system accepts these file formats:

| Format | Extension | Example use |
|---|---|---|
| CSV (comma separated) | `.csv` | Position data, equity prices, reference data |
| TSV (tab separated) | `.tsv` | Same as CSV but tab-delimited |
| Excel | `.xlsx` / `.xls` | Any structured data in a spreadsheet |
| JSON | `.json` | Structured records |
| Text | `.txt` | Pipe or semicolon delimited files |
| Parquet | `.parquet` | Large compressed datasets |

**Maximum file size: 100 MB per file.**

---

## Step-by-Step: How to Upload a File

### Step 1 — Go to Upload

From the menu, click **Upload** → **New Upload**.

---

### Step 2 — Select Your File

Click **Choose File** and pick your file. The system will immediately:

- Check the file format is supported
- Check the file is not empty and not over 100 MB
- Detect the delimiter automatically (comma, tab, pipe, semicolon)
- Detect the encoding (UTF-8, etc.)
- Show you a **preview** of the first few rows and column names

If there are any problems with the file (wrong format, empty, too large), an error message will appear here and you will not be able to proceed.

> **Tip:** If your CSV uses a pipe `|` or semicolon `;` as separator, the system detects it automatically — you do not need to change anything.

---

### Step 3 — Review the Preview

Before uploading, you will see:

- Column names detected from the header row
- Column data types (text, number, date) detected automatically
- A sample of up to 100 rows
- Any **warnings** (e.g. duplicate rows found in the file)

You can review the column mapping here. If column names need to be adjusted, you can edit them at this stage.

---

### Step 4 — Submit

Click **Upload**. The file is saved and validated against the target table configuration.

---

### Step 5 — Data is Loaded into the System

Once submitted, the data is inserted into the target Kudu/Hive table automatically. You will see a summary of:

- How many rows were loaded successfully
- How many rows had errors (with reasons)
- Total time taken

---

## What Happens If I Upload the Same File Format Again?

This is the most important thing to understand.

### Uploading the same format file a second time — **it replaces the previous data**

The system uses **overwrite mode** for most table types. This means:

- If you upload `equity_prices_20260611.csv` today, it loads into the target table.
- If you upload another file of the **same format** tomorrow, the new data **replaces** the old data in the target table.

**This is by design** — each daily upload is a full refresh of that dataset.

### What "same format" means

The format is determined by the **datasource configuration** (`cis_datasource_mng`), not the file name. Each datasource config is linked to a specific target table. Any file that matches a datasource config will load into that table, replacing what was there before.

---

## Uploading Multiple Files of the Same Format

| Scenario | What happens |
|---|---|
| Upload file A of format X, then file B of format X | File B **replaces** file A in the target table |
| Upload file A of format X, then file C of format Y | Both loaded into **different** target tables — no conflict |
| Upload file A of format X twice (exact same file) | Second upload replaces first — result is the same data |

> **Rule of thumb:** One upload per format per day. If you need to re-upload because the first file had errors, just upload the corrected file — it will overwrite the previous one cleanly.

---

## Duplicate Rows in Your File

If your file itself contains **duplicate rows** (same data repeated), the system will:

1. Show a **warning** in the preview step (e.g. "Found 3 duplicate row(s) in source file")
2. Still allow you to proceed
3. Automatically remove duplicates before loading — only unique rows are inserted

You do not need to manually clean duplicate rows from your file.

---

## Special Case — Equity Price Upload

Equity price files work slightly differently. Instead of replacing all prices, each row is **upserted** (insert or update) by security + price date. This means:

- Uploading prices for new securities adds them
- Uploading updated prices for existing securities on the same date **updates** them
- Prices for other securities not in the file are **not affected**

This allows you to upload partial price files (e.g. just today's prices) without wiping out historical prices.

---

## Common Errors and What to Do

| Error message | Cause | Fix |
|---|---|---|
| "Unsupported file format" | File extension not in the allowed list | Convert to CSV, Excel, or JSON |
| "File size exceeds 100 MB" | File too large | Split into smaller files and upload separately |
| "File is empty" | No data in the file | Check the file and re-upload |
| "File contains only a header row" | File has column names but no data rows | Add data rows to the file |
| "CSV parsing error" | File is corrupted or has unusual encoding | Save as UTF-8 CSV and re-upload |
| "No datasource configuration found" | File name not matched to a known format | Contact your system administrator to register the format |

---

## Upload History

Every upload is recorded. You can view past uploads at **Upload → Upload List**, which shows:

- File name and size
- Upload date and who uploaded it
- Status (Completed / Failed)
- Number of rows loaded
- Any errors from that run

---

## Quick Reference

```
Supported formats : CSV, TSV, TXT, XLSX, XLS, JSON, Parquet
Max file size     : 100 MB
Duplicate rows    : Automatically removed before load
Same format again : Overwrites previous data in target table
Equity prices     : Upsert by security + date (partial files OK)
```
