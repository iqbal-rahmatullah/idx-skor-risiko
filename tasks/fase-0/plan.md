# Rencana Fase 0 — Fondasi

## Konteks

PRD §18 Fase 0 selesai bila `python -m bot` membalas `/start` **dan** satu snapshot ANTM tersimpan di database. Sudah ada: repo (1 commit), `CLAUDE.md`, PRD, `.env.example`, ruff, pytest, `bot/config.py`, `bot/__main__.py` (/start), `bot/data/tickers.json` (962 emiten), `scripts/fetch_tickers.py`, 25 fixture respons Sectors asli di `tests/fixtures/`. `.env` sudah berisi `SECTORS_API_KEY` dan `TELEGRAM_BOT_TOKEN`.

Yang belum: klien Sectors, skema `TickerSnapshot`, database, dan alur ambil → normalisasi → simpan.

Keputusan pengguna:

- **Snapshot dinormalisasi penuh** — semua jebakan data Sectors ditangani sekali di sini, konsumen (indikator Fase 1, Developer A) tidak perlu tahu.
- **Cakupan semua endpoint PRD §11** — ±12–15 kredit per snapshot bila live.
- **Pengembangan memakai data mock**, bukan API langsung. Klien Sectors default ke mode offline yang melayani fixture dari `tests/fixtures/sectors/`; panggilan live hanya bila `SECTORS_OFFLINE=false` ditulis eksplisit di `.env`. Seluruh Fase 0 selesai dengan **0 kredit**. Mode yang sama nanti dipakai untuk demo tanpa internet (PRD §14).

## Aturan normalisasi (berlaku di semua tugas)

- Semua array riwayat diurutkan **naik** (tertua dulu) — `quarterly` dan `composition` dibalik, `dividend` diurutkan per `ex_date`.
- Semua persentase disimpan **desimal** (`0.35` = 35%). `share_percentage` string → float.
- Simbol tanpa `.JK`. Nama field kuartalan disamakan dengan tahunan (`total_current_asset` → `current_assets`).
- Rasio tahunan diratakan dari grup (`capital.capital_adequacy_ratio` → `capital_adequacy_ratio`), gagal keras bila ada nama bentrok.
- `null` tetap `None`, kunci kosong `null` di `corporate_actions` → `[]`. Tidak pernah diganti 0.
- Semua jendela waktu dihitung dari `as_of` (= `overview.latest_close_date`), tidak dari jam sistem.
- Pemisahan: `fetch_raw()` (IO) terpisah dari `normalize(raw) -> TickerSnapshot` (fungsi murni), supaya tes jalan dari fixture tanpa jaringan.

## Graf dependensi

```
config (ada) ─► T1 klien Sectors + mode mock ─► T2 irisan pertama end-to-end (report → model → DB → CLI)
                                     ├─► T3 harga + split
                                     ├─► T4 keuangan
                                     ├─► T5 kepemilikan + broker
                                     └─► T6 peristiwa
                                           └─► T7 rekam fixture lengkap + tes determinisme ─► Checkpoint keluar
```

T3–T6 saling lepas setelah T2; boleh dikerjakan urut mana pun.

## Tugas

### T1 — Klien Sectors dan mode mock

File: `bot/sectors/client.py`, `bot/sectors/fixtures.py`, `bot/config.py` (+`sectors_offline: bool = True`), `tests/test_sectors_client.py`; refaktor `scripts/fetch_tickers.py` memakai klien ini.

- Rapikan fixture ke skema satu pola: `tests/fixtures/sectors/{endpoint}/{TICKER}.json` (misalnya `daily/ANTM.json`, `report/BBCA.json`, `suspensions/_market.json`). Fixture eksplorasi screener tetap di tempatnya.
- `SectorsClient` membungkus `httpx.AsyncClient`: base `https://api.sectors.app/v2`, header `Authorization: <key>` tanpa `Bearer`, `verify=certifi.where()`.
- Mode offline: klien memakai `httpx.MockTransport` yang memetakan path ke file fixture. Parameter query diabaikan — fixture berisi respons penuh, dan normalisasi tetap memfilter per simbol dan jendela `as_of`. Fixture tidak ada → `SectorsError` jelas ("fixture belum ada: daily/BBRI"), tidak pernah jatuh ke jaringan.
- `get(path, **params)` → JSON; catat kredit dari header `limit-consumption` (None bila tidak ada).
- `get_all_pages(path, **params)` → ikuti `pagination.next_offset` (logika dipindah dari `fetch_tickers.py`).
- Error non-2xx → `SectorsError(status, code, message)`; pesan tidak pernah memuat key.

**Terima bila:** tes membuktikan header persis, paginasi 3 halaman tergabung, 401 jadi `SectorsError` tanpa key di `str()`, mode offline melayani `report/ANTM` dari file dan menolak ticker tanpa fixture. Default `sectors_offline=True` diuji. `fetch_tickers.py` tidak dijalankan ulang di fase ini (butuh live).

### T2 — Irisan pertama: overview + valuasi, sampai tersimpan

File: `bot/snapshot/models.py`, `bot/snapshot/build.py`, `bot/snapshot/__main__.py`, `bot/tickers.py`, `bot/db/__init__.py`, `bot/config.py` (+`database_url`, default `sqlite:///sectors_hackathon.db`), `pyproject.toml` (+`sqlalchemy>=2`, `pydantic>=2`).

- Model pydantic `TickerSnapshot` dengan semua bagian PRD §11; bagian yang belum diisi bertipe opsional sampai tugasnya selesai. `idx_lists` = `None` (diisi Fase 1 dari scrape IDX).
- Isi: `symbol`, `as_of`, `sector`, `sub_sector`, `listing_board`, `overview` (market_cap, tags, indices, last_close_price), `valuation` (riwayat naik, forward_pe, intrinsic_value, eps), `sources[{endpoint, fetched_at, credits}]`.
- DB: satu tabel `ticker_snapshots(symbol, as_of, data JSON, created_at)`, unik `(symbol, as_of)`; `save_snapshot`, `get_snapshot`.
- CLI `uv run python -m bot.snapshot ANTM`: validasi ticker di `bot/data/tickers.json` **sebelum** panggilan API → ambil report → kalau `(symbol, as_of)` sudah ada di DB, berhenti tanpa panggilan lain → normalisasi → simpan → cetak ringkasan (as_of, total kredit, jumlah field null).

**Terima bila:** tes `normalize` dari fixture report ANTM dan BBCA; tes DB round-trip SQLite in-memory; ticker `XXXX` ditolak tanpa request apa pun. CLI untuk ANTM dalam mode offline: baris muncul di DB dengan `as_of` 2026-09-22.

### T3 — Harga dan split

- `/daily` `as_of−89 hari … as_of` → `price` `[{date, open, high, low, close, volume}]` naik. `splits` dari `corporate_actions.stock_split`.

**Terima bila:** tes dari `daily_ANTM_90d.json`: 63 baris, tanggal naik ketat, tanpa duplikat.

### T4 — Keuangan

- Tahunan (`historical_financials`) dan rasio tahunan (diratakan) naik per tahun; `/financials/quarterly` `n_quarters=2` naik per tanggal, `financials_sector_metrics` diratakan, nama field disamakan.

**Terima bila:** tes ANTM (non-bank) dan BBCA (bank: `capital_adequacy_ratio`, `loan_to_deposit_ratio`, `gross_loan`, `allowance_for_loans` ada); null di data asli tetap `None`; tahun terakhir tidak diambil dari indeks 0.

### T5 — Kepemilikan dan broker

- `holders[{name, share}]` float; `free_float` = share baris `"Public"` (None bila tidak ada); komposisi bulanan naik; filings insider `as_of−90 hari` (semua halaman); broker top 10 untuk tanggal `as_of`.
- **Verifikasi satuan `share_percentage_transaction`** (CLAUDE.md bilang persen, slide menulis `0.4`): cocokkan dengan `amount_transaction / shares` di `filings_BBCA_all.json`, lalu simpan desimal dan perbaiki CLAUDE.md bila salah.

**Terima bila:** tes free float ANTM = 0.35, AEGS papan `Acceleration`; komposisi naik; broker urut `rank`.

### T6 — Peristiwa

- `/news?symbols=TICKER` `as_of−30 hari` (semua halaman), `/suspensions?symbol=TICKER` `as_of−90 hari`, `/company/corporate-actions` (dividend naik per `ex_date`, `null` → `[]`).

**Terima bila:** tes dividend ANTM terurut (fixture asli tidak terurut); `warrant`/`bonus` null → `[]`; paginasi lewat klien T1.

### T7 — Determinisme dan snapshot ANTM lengkap dari mock

- Tes: `normalize(raw)` dua kali → `model_dump_json()` identik byte per byte; tidak ada angka 0 yang di data asli null; grep fixture tidak memuat key.
- Snapshot ANTM penuh dibangun dari mock: semua bagian terisi kecuali `idx_lists`.
- BBCA hanya punya fixture report, quarterly, dan filings. Itu cukup untuk tes varian bank di T4; fixture BBCA lainnya direkam di Fase 1 saat indikator bank butuh.

**Terima bila:** `uv run pytest` hijau tanpa jaringan; `uv run ruff check .` bersih.

## Checkpoint keluar Fase 0

1. `uv run python -m bot`, kirim `/start` dari Telegram → dibalas "Halo, bot Skor Risiko aktif." (manual).
2. `uv run python -m bot.snapshot ANTM` (offline) → baris ANTM tersimpan; jalankan ulang → tidak ada panggilan selain report (cache per tanggal).
3. _Opsional, butuh persetujuan:_ satu kali `SECTORS_OFFLINE=false uv run python -m bot.snapshot ANTM` (±12–15 kredit) untuk memastikan normalisasi juga lolos dengan respons live dan parameter persis builder.
4. Kirim `TickerSnapshot.model_json_schema()` + contoh snapshot ANTM ke Developer A untuk disepakati (langkah manusia).
5. Perbarui `CLAUDE.md`: bagian Struktur (`snapshot/models.py`, `sectors/fixtures.py`, `tickers.py`, `db/`) dan aturan "pengembangan dan tes memakai mode offline; live hanya dengan `SECTORS_OFFLINE=false` eksplisit".

## Di luar Fase 0

Scrape IDX (`idx_lists`), riwayat harga lokal yang bertambah tiap putaran, distribusi subsektor lewat screener, saran ticker terdekat — Fase 1, 2, dan 4.
