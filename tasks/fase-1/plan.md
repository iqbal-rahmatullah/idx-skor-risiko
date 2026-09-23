# Rencana Fase 1 — Mesin aturan inti

## Konteks

Fase 0 selesai: `TickerSnapshot` ternormalisasi tersimpan di SQLite, klien Sectors punya mode offline, 49 tes hijau. Fase 1 (PRD §18) mengubah snapshot menjadi `indicators.json`: 10 indikator bersumber regulator, status, skor pilar, skor akhir, grade. **Keluar:** `indicators.json` untuk ANTM dan BBCA benar dan lulus tes.

Keputusan pengguna untuk fase ini:
- **Data IDX** (notasi khusus, Papan Pemantauan Khusus) dari **file manual** di `bot/data/idx/`, bukan scraper. Scraper menyusul di Fase 4.
- **Jendela 6 bulan** lewat **dua panggilan `/daily`** (±180 hari). Tabel harga inkremental tetap di Fase 4.
- **Rekam live sekali** (±7 panggilan, ±8–10 kredit) untuk melengkapi fixture BBCA dan jendela `/daily` kedua. Selebihnya offline.
- **`ldr_rim` satu sisi:** hanya > 94% bermasalah; < 84% tampil sebagai catatan, tidak menaikkan skor.
- **Status per indikator mengikuti pita dari peraturannya sendiri**, tidak ada margin karangan:

| Indikator | Pita | Dasar |
|---|---|---|
| `negative_equity`, `no_revenue`, `sub_51_price`, `special_notation`, `special_monitoring_board`, `suspension_uma` | biner: bermasalah / wajar | tidak punya skala |
| `car` | < 8% bermasalah · 8–11% perhatian · > 11% kuat | jenjang minimum per profil risiko, POJK 11/POJK.03/2016 |
| `free_float` (Main, Development, lainnya) | < 12,5% bermasalah · 12,5–15% perhatian · ≥ 15% wajar | tonggak transisi I-A (12,5% paling lambat Maret 2027) |
| `free_float` (Acceleration) | < 7,5% bermasalah · lainnya wajar | tidak ada tonggak transisi yang diketahui |
| `daily_liquidity` | kedua syarat → bermasalah · salah satu → perhatian · tidak ada → wajar | kata "dan" di kriteria 7 I-X |
| `ldr_rim` | > 94% bermasalah · 84–94% wajar · < 84% wajar + catatan | keputusan tim |

`kuat` tidak wajib ada di setiap indikator. `perhatian` berbobot nol, jadi pita ini tidak mengubah skor — hanya kata di kartu.

Tidak ada commit; pengguna mereview dulu. Selama pengembangan jalankan CLI dengan `SECTORS_OFFLINE=true`.


## Revisi setelah T0 (sumber resmi dibaca)

- I-X yang berlaku (Kep-00035/BEI/06-2025) memakai jendela **3 bulan**: satu jendela `/daily` 90 hari cukup, T1 tidak menambah jendela kedua.
- `sub_51_price` kumulatif (III.1.1): < Rp51 + likuiditas rendah → bermasalah; < Rp51 saja → perhatian; Papan Akselerasi → `tidak_berlaku` (III.2).
- Dividen tunai dalam 12 bulan (III.3) → `daily_liquidity` dan `sub_51_price` `tidak_berlaku` dengan catatan.
- `free_float` per kapitalisasi: ≥ Rp5 T → < 12,5% bermasalah · 12,5–15% perhatian; < Rp5 T → < 15% perhatian. Papan Akselerasi < 7,5% bermasalah.
- `car`: < 8% bermasalah · 8–14% perhatian · > 14% kuat; buffer KBMI 3–4 sebagai keterangan.
- `ldr_rim` bersumber PADG 23/2025 Pasal 7 jo. PADG 18/2026.
- `special_notation`: bermasalah bila ada huruf selain X, N, I. Tidak ada cadangan `listing_board == "Watchlist"` (hanya 126/198 cocok dengan X).
- Data notasi diambil dari API `idx.id` ke `bot/data/idx/notasi_khusus.csv` (184 emiten, 22 Sep 2026).

## Keputusan desain

- **Fungsi murni.** Setiap indikator `(snap: TickerSnapshot) -> Indicator`; tidak membaca DB atau jam sistem. `build_indicators(snap)` deterministik byte per byte.
- **`Indicator`** (pydantic, `bot/risk/models.py`): `id, pillar, label, status, is_new, since, value, display, threshold, source, source_type, weight, evidence_path, note`. `is_new`/`since` bernilai `null` sampai Fase 4 (butuh pembanding snapshot). `display` dan `threshold` diformat kode dengan format Indonesia (`35%`, `7,5%`, `Rp5 juta`, `10.000 lembar`) di `bot/risk/format.py`.
- **`thresholds.py`** menyimpan setiap ambang sebagai `Rule(value, source, source_type, effective, url)`; pita free float menyimpan `berlaku_sampai` karena berubah setelah transisi 2027.
- **Varian bank** dipilih dari `sector == "Financials"`. Field bank yang null → `tidak_tersedia` (asuransi dan pembiayaan).
- **Split saham:** kalau ada split dengan `ex_date` di jendela 6 bulan, rata-rata harga hanya memakai bar sesudah split terakhir. Split tanpa tanggal yang dikenali → `tidak_tersedia`, bukan tebakan.
- **Skor:** `skor_pilar = Σ bobot(bermasalah) / Σ bobot(bisa dinilai) × 100`; pilar tanpa indikator yang bisa dinilai bernilai `null` dan tidak ikut rata-rata. Skor akhir = rata-rata pilar yang ada (bobot pilar sama, dicatat di `thresholds.py`), dibulatkan `ROUND_HALF_UP` ke bilangan bulat; grade dari tabel PRD §9.
- **Indikator yang belum dibangun** (17 lainnya) tidak dimasukkan — bukan `tidak_tersedia`, karena status itu berarti datanya null.
- **`indicators.json` Fase 1:** `symbol, as_of, trigger, score{value, grade}, summary_counts, pillars[{id, label, score, indicators[]}], dismissed[] (kosong sampai Fase 4), unavailable[]`. `context` ditambahkan di Fase 3.

## Graf dependensi

```
T0 sumber & PRD ─┐
T1 rekam fixture ┴─► T2 irisan pertama: free_float → skor → grade → indicators.json → CLI
                        ├─► T3 likuiditas + harga < Rp51 (butuh jendela 180 hari dari T1)
                        ├─► T4 pilar 2 non-bank + bank
                        ├─► T5 suspensi
                        └─► T6 data IDX → notasi khusus + Papan Pemantauan Khusus
                                 └─► T7 golden ANTM & BBCA, determinisme, dokumen ─► Checkpoint keluar
```

## Tugas

### T0 — Sumber, tanggal berlaku, dan PRD
- Baca dokumen resmi (tautan di lampiran PRD) dan catat untuk tiap ambang: nomor peraturan, pasal/kriteria, tanggal berlaku, URL. Wajib: I-A (15% dan tonggak 12,5% 2027, tanggal persis), I-X (nomor keputusan, tanggal berlaku, kriteria 1/3/5/7), POJK 11/2016 jo. 27/2022 (jenjang CAR), PADG RIM 84–94% (masih berlaku?), II-A (suspensi), daftar arti huruf notasi khusus IDX.
- Perbarui PRD §10 dulu (aturan inti 6): kolom pita status untuk `car`, `free_float`, `daily_liquidity`; `ldr_rim` satu sisi; catatan biner untuk enam lainnya.

**Terima bila:** setiap ambang Fase 1 punya sumber + tanggal yang bisa dibuka. **Kalau ada yang tidak bisa diverifikasi (situs diblokir, tanggal tidak tertulis), berhenti dan tanya** — tidak ada tanggal karangan.

### T1 — Jendela `/daily` 180 hari dan rekam fixture
File: `bot/snapshot/build.py`, `bot/sectors/client.py` (`recording_transport`), `scripts/record_fixtures.py`.
- `fetch_eod` mengambil dua jendela: `as_of−90…as_of` dan `as_of−180…as_of−91`; `normalize_price` memotong ke 180 hari.
- `recording_transport`: fixture yang sudah ada dilayani dari file; yang belum → live lalu disimpan ke path fixture. `/daily` selalu live dan digabung (union per tanggal) ke `daily/{SYMBOL}.json`.
- `uv run python -m scripts.record_fixtures ANTM BBCA` memakai `take_snapshot` sungguhan dengan DB in-memory, sehingga parameternya identik dengan builder. Perkiraan live: ANTM 2 (`/daily`), BBCA 5 (`/daily` ×2, aksi korporasi, komposisi, broker).

**Terima bila:** jendela kedua mengembalikan data tanggal lama (bukan dipotong ke 90 hari terakhir) — kalau ternyata dipotong, berhenti dan laporkan; snapshot BBCA offline terbangun penuh; tes kunci-tidak-bocor tetap hijau; kredit terpakai dilaporkan.

### T2 — Irisan pertama: `free_float` sampai `indicators.json`
File: `bot/risk/models.py`, `bot/risk/format.py`, `bot/risk/thresholds.py`, `bot/risk/indicators/p1_ukuran.py`, `bot/risk/score.py`, `bot/risk/build_json.py`, `bot/risk/__main__.py`, `tests/test_risk.py`.
- `free_float` dengan pita per papan dan tanggal berlaku; papan tak dikenal → pita paling ketat.
- `score.py`, `build_json.py`, CLI `uv run python -m bot.risk ANTM` (memakai `take_snapshot` yang ada, mencetak `indicators.json`).

**Terima bila:** tes ANTM 35% → wajar; AEGS (Acceleration) 39,77% → wajar; sintetis 10% di Main → bermasalah, 13% → perhatian, 10% di Acceleration → wajar, papan `"Watchlist"` memakai pita ketat, `free_float=None` → `tidak_tersedia` dan masuk `unavailable`; skor/grade untuk kombinasi status; pilar tanpa indikator → `null`, tidak ikut rata-rata; format `7,5%` dengan koma.

### T3 — `daily_liquidity` dan `sub_51_price`
- Nilai transaksi = `close × volume` per hari (tidak ada field nilai di `/daily`; dicatat sebagai pendekatan). `display` memuat jumlah hari bursa yang dipakai.

**Terima bila:** tes sintetis untuk tiga pita likuiditas; harga rata-rata Rp50 → bermasalah; split di tengah jendela → hanya bar sesudah split; split tanpa `ex_date` → `tidak_tersedia`; ANTM dari fixture 180 hari → wajar dengan jumlah hari > 63.

### T4 — Pilar 2: non-bank dan bank
File: `bot/risk/indicators/p2_keuangan.py`.
- Non-bank: `negative_equity` (ekuitas kuartalan terbaru non-null, jatuh ke tahunan), `no_revenue` (pendapatan terbaru nol, atau sama dengan kuartal sebelumnya).
- Bank: `car` (tiga pita), `ldr_rim` (satu sisi + catatan). Label LDR menyebut "proksi RIM".

**Terima bila:** ANTM → keduanya wajar; BBCA → CAR 30,4% kuat, LDR 75,9% wajar dengan catatan "di bawah rentang RIM 84%"; sintetis ekuitas −1 → bermasalah; pendapatan sama dua kuartal → bermasalah; bank dengan CAR null → `tidak_tersedia`; tidak ada indikator non-bank di snapshot bank dan sebaliknya.

### T5 — `suspension_uma`
File: `bot/risk/indicators/p6_peristiwa.py`.
- Suspensi dengan `suspension_date ≥ as_of−90 hari`, termasuk yang bertanggal sesudah `as_of`. Label menyebut UMA belum tercakup (tidak ada di Sectors).

**Terima bila:** NASI dengan `as_of` 21 Sep → bermasalah (suspensi berlaku 22 Sep); ANTM → wajar.

### T6 — Data IDX, notasi khusus, dan Papan Pemantauan Khusus
File: `bot/data/idx/notasi_khusus.csv` (`kode,notasi,tanggal_data,sumber_url`), `bot/idx/lists.py`, `bot/snapshot/models.py` (+`idx_lists: IdxLists | None`), `bot/snapshot/build.py`.
- Arti huruf dan penanda "bermasalah" di `thresholds.py`, bersumber pengumuman BEI (dari T0).
- `idx_lists` dibaca dari CSV saat snapshot dibuat **dan** disegarkan saat cache dipakai (file lokal, 0 panggilan). File tidak ada → `None` → kedua indikator `tidak_tersedia`, kecuali `listing_board == "Watchlist"` yang menandai Papan Pemantauan Khusus dengan sumber "Sectors listing_board (sinyal pendukung)".
- Isi CSV disalin manual dari idx.co.id — **langkah manusia**; tes memakai CSV kecil di `tests/fixtures/idx/`.

**Terima bila:** notasi `X` → Papan Pemantauan Khusus bermasalah; `E` → notasi khusus bermasalah; huruf yang bukan penanda masalah (bila ada, dari T0) → wajar; tanpa CSV + board Watchlist → bermasalah dengan sumber pendukung; tanpa CSV + board Main → `tidak_tersedia`.

### T7 — Golden file, determinisme, dokumen
- `tests/golden/indicators_ANTM.json` dan `indicators_BBCA.json`, dicocokkan byte per byte. Nilai di golden diperiksa manual terhadap fixture sebelum disimpan.
- Tes determinisme: `build_indicators` dua kali identik; snapshot dari raw yang diacak menghasilkan JSON yang sama.
- Perbarui `CLAUDE.md` (struktur `bot/risk/`, `bot/idx/`, CLI baru, cara memperbarui CSV IDX) dan `tasks/todo.md`.

**Terima bila:** `uv run pytest` hijau tanpa jaringan; `uv run ruff check .` bersih.

## Checkpoint

1. **Setelah T0:** tunjukkan tabel sumber + tanggal ke pengguna sebelum menulis `thresholds.py`.
2. **Setelah T2:** tunjukkan contoh `indicators.json` ANTM (satu indikator) — bentuk JSON dikunci sebelum 9 indikator lain ditulis.
3. **Keluar Fase 1:** `SECTORS_OFFLINE=true uv run python -m bot.risk ANTM` dan `BBCA` mencetak `indicators.json` yang cocok dengan golden. Perkiraan BBCA: pilar 1 = 0, pilar 2 = 0 (CAR kuat, LDR wajar), pilar 6 tergantung CSV → grade A.

## Di luar Fase 1

`is_new`/`since` dan `dismissed` (Fase 4), `context` (Fase 3), 17 indikator lainnya (Fase 5), scraper IDX dan tabel harga inkremental (Fase 4), UMA.
