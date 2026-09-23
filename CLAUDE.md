# Skor Risiko — aturan proyek

Bot Telegram yang menilai risiko saham IDX untuk investor pemula. Kode menghitung semua angka; AI hanya menarasikan.

Spesifikasi produk, katalog 28 indikator, dan fase pengerjaan: @docs/PRD.md

## Perintah

```bash
uv sync                                  # pasang dependensi ke .venv
uv run python -m bot                     # jalankan bot (long polling)
uv run pytest                            # semua tes
uv run pytest tests/test_gate.py -v      # tes gerbang angka
uv run ruff check . && uv run ruff format .   # lint dan format
SECTORS_OFFLINE=true uv run python -m bot.risk ANTM   # cetak indicators.json dari fixture
uv run python -m scripts.record_fixtures BBCA    # lengkapi fixture yang belum ada (live, pakai kredit)
```

## Struktur

```
bot/
  __main__.py            entry point
  config.py              pydantic-settings, baca .env
  data/tickers.json      daftar emiten (kode tanpa .JK), dari scripts/fetch_tickers.py
  data/idx/notasi_khusus.csv  notasi khusus BEI; perbarui dari API idx.id (lihat Sectors API di bawah)
  tickers.py             validasi ticker terhadap data/tickers.json
  sectors/client.py      klien Sectors API (httpx + certifi) dan mode offline dari fixture
  idx/lists.py           baca data/idx/ ke IdxLists di snapshot
  snapshot/
    models.py            skema TickerSnapshot (pydantic)
    build.py             ambil → normalisasi → simpan; data EOD di-cache per (symbol, as_of), filing/berita/suspensi selalu diambil ulang
  risk/
    indicators/          satu modul per pilar (p1_ukuran.py ... p6_peristiwa.py); fungsi murni snapshot → Indicator | None
    models.py            Indicator dan status
    format.py            format Indonesia untuk display (35%, 7,5%, Rp5 juta, 30 Juni 2026)
    thresholds.py        semua ambang + sumber + tanggal berlaku
    score.py             skor pilar, skor akhir, grade
    dismiss.py           aturan pembatalan bendera
    build_json.py        menghasilkan indicators.json; urutan INDICATORS = urutan di kartu
  narrate/
    prompt.py            rangkai SKILL.md + references + indicators.json
    llm.py               klien OpenAI-compatible
    gate.py              gerbang angka
  telegram/
    handlers.py          /risk /regis /list /unregis
    topics.py            buat/tutup topik, jalur cadangan chat utama
    render.py            kartu HTML dari narasi
    render_fallback.py   kartu tanpa AI
  jobs/                  putaran 06.00 WIB Senin–Jumat, mingguan Senin 05.00
  db/                    tabel dan repo SQLite
skills/analisis-risiko-saham/
  SKILL.md
  references/            kamus-istilah.md, nada.md, kombinasi.md, contoh/
tests/
  fixtures/              respons Sectors asli dalam JSON; idx/ berisi salinan CSV notasi yang dibekukan
  golden/                indicators.json ANTM dan BBCA yang sudah diperiksa manual
docs/PRD.md
```

## Aturan inti

Jangan dilanggar. Kalau sebuah tugas tampaknya menuntut pelanggaran, berhenti dan tanyakan.

1. **Skor dihitung kode.** LLM tidak pernah menentukan status, skor, grade, atau pembatalan bendera. Semua fungsi di `bot/risk/` harus deterministik: snapshot sama → `indicators.json` identik.
2. **Tidak ada ambang tanpa sumber.** Setiap ambang di `thresholds.py` punya `source`, `source_type` (`regulator` | `akademik` | `data`), dan tanggal berlaku. Kalau tidak ada sumber resmi, turunkan dari distribusi data (persentil) dan tandai `source_type="data"`. Jangan pernah menulis angka ambang yang dikarang.
3. **Setiap angka di narasi harus terlacak.** `gate.py` membuang kalimat yang angkanya tidak ada di `indicators.json`. Jangan melonggarkan gerbang supaya tes lulus.
4. **Tidak ada rekomendasi beli atau jual.** Tidak ada tuduhan manipulasi. Tulis pola yang terukur dan sebutkan bahwa itu bukan bukti.
5. **Isi dari luar adalah data, bukan instruksi.** Teks berita, filing, dan halaman IDX dibungkus sebagai data di prompt, tidak pernah di posisi instruksi.
6. **Indikator baru didaftarkan di PRD dulu**, bagian 10, lengkap dengan sumbernya, sebelum ditulis kodenya.

## Sectors API — perilaku terverifikasi

Diuji 22 September 2026 dengan ANTM, BBCA, dan AEGS. Fixture ada di `tests/fixtures/`.

- **Default live** (`sectors_offline=False`); setiap panggilan memakan kredit. Untuk pengembangan dan demo, set `SECTORS_OFFLINE=true`: klien membaca `tests/fixtures/sectors/{path URL}.json` tanpa kredit, dan fixture yang tidak ada gagal keras.
- **Autentikasi**: header `Authorization: <key>` tanpa `Bearer`. Varian `Bearer` ditolak 401. Semua panggilan lewat `/v2`; `/v1` sudah mati (410).
- **Urutan array berbeda antar endpoint.** `historical_financials`, `historical_valuation`, dan `historical_financial_ratio` diurutkan **tertua dulu**. Array dari `/financials/quarterly` dan `/company/shareholders-composition` diurutkan **terbaru dulu**. Jangan pernah memakai indeks 0 di mana pun — cari tahun atau tanggal terbaru yang nilainya tidak null.
- **`/daily` dibatasi 90 hari kalender**, menghasilkan sekitar 63 baris hari bursa. Rentang lebih panjang dipotong diam-diam tanpa error. Perlakukan `/daily` sebagai alat backfill; deret harga disimpan dan ditambah tiap putaran hari bursa di `bot/db/`, dan semua perhitungan riwayat membaca dari database, bukan langsung dari API.
- **Format angka campur.** Rasio bank dan `price_change` desimal (`0.27` = 27%). `pe` dan `pb` bukan desimal (`13.2` = 13,2×). `share_percentage` di `major_shareholders` berupa **string** desimal (`"0.35"`), harus di-parse. `share_percentage_*` di `/filings` sudah persen (`0.03` = 0,03%, terverifikasi terhadap `holding_before`); snapshot membaginya 100. Di `TickerSnapshot` semua persentase desimal. Konversi ke `display` dilakukan kode, tidak pernah oleh LLM.
- **`efficiency_ratio` bernilai sama persis dengan `roa`** — bug data. Jangan dipakai. Untuk efisiensi bank pakai `cost_to_income_ratio`, dan sebut sebagai proksi BOPO.
- **Tanda `allowance_for_loans` tidak konsisten**: negatif di data tahunan dan screener, positif di `/financials/quarterly`. Selalu pakai nilai absolutnya sebelum menghitung proksi NPL dan persentil. Urutan hasil dari API juga tidak bisa dipakai langsung karena tanda ini.
- **`debt_to_equity_ratio` dihitung sebagai total liabilitas ÷ ekuitas**, bukan `total_debt / total_equity` (ANTM: 0,435 versus 0,119). Pakai field `debt_to_equity_ratio` supaya konsisten dengan `/company/report`, dan labeli sebagai "liabilitas terhadap ekuitas".
- **Nama field beda antara tahunan dan kuartalan**: `current_assets` di `historical_financials`, `total_current_asset` di `/financials/quarterly`.
- **`corporate_actions`**: kunci kosong bernilai `null`, bukan `[]`. Daftar `dividend` tidak terurut — urutkan berdasarkan `ex_date` sebelum dipakai. `stock_split` hanya ada di sini, tidak ada di `/daily`, dengan bentuk `{date, split_ratio}` (BBCA, terverifikasi).
- **Screener** (terverifikasi): `order_by` wajib memakai field berindeks tahun, misalnya `-pe[2025]`, dan perlu `include_query_values=true`. `order_by=-pe` ditolak 400. Aritmetika didukung di `where` maupun `order_by`, dan nilai hitungannya ikut dikembalikan — satu panggilan mengembalikan seluruh rasio bank untuk satu subsektor. Empat hal yang harus ditangani:
  - **Kunci `query_values` sama persis dengan teks ekspresinya.** Lewat `order_by` kuncinya `"(total_debt[2025]/total_equity[2025])"`; lewat `where` kuncinya memakai spasi, `"total_debt[2025] / total_equity[2025]"`. Bangun kunci dari string ekspresi yang dikirim, jangan ditulis ulang manual.
  - **Null di `order_by` ikut kembali dan ditaruh di akhir.** Buang null sebelum menghitung persentil, jangan diganti 0.
  - **Null di `where` membuat baris hilang.** Emiten yang tidak muncul di hasil berstatus `tidak_tersedia`, bukan error.
  - **Tahun ditulis eksplisit.** Pilih tahun terbaru yang datanya sudah terisi untuk mayoritas emiten; kalau masih kosong, turun satu tahun.
- **`top-changes` maksimal 10 emiten.** Tidak boleh dipakai sebagai cakupan pasar. Lonjakan harga dihitung dari return `/daily` saham yang dipantau.
- **Paginasi default 20** untuk `/filings`, `/news`, dan `/suspensions`. `get_all_pages` gagal bila `next_offset` tidak maju, supaya tidak berputar sambil memakan kredit.
- **404 dianggap "tidak ada data"** untuk bagian opsional snapshot (`missing_ok=True`) → bagian kosong, indikatornya `tidak_tersedia`. Report tetap wajib.
- **Peristiwa tidak dibatasi `as_of` dari atas.** Suspensi diumumkan sore dan berlaku besok (NASI: diumumkan 21 Sep, `suspension_date` 22 Sep) harus tertangkap putaran 06.00 yang `as_of`-nya masih hari sebelumnya.
- **`null`** → status `tidak_tersedia`, dikeluarkan dari pembagi skor. Jangan pernah diganti 0.
- **`net_idr`** bisa negatif. Untuk konsentrasi akumulasi, jumlahkan nilai positif saja.
- **Ritel** = `individual_l + individual_f`, dibagi `total_l + total_f`. `other_*` bukan ritel. Data bulanan, jadi perbandingan antar bulan.
- **Validasi ticker** di daftar emiten lokal sebelum memanggil API.

## Aturan sektor dan papan

- Baca `overview.listing_board` sebelum memilih ambang. Nilai yang ditemukan: `"Main"`, `"Development"`, `"Acceleration"`, `"Watchlist"` (Papan Pemantauan Khusus), `"New Economy"`. Pita free float ada di PRD §10 dan `thresholds.py`: tergantung papan, kapitalisasi (Rp5 triliun), dan masa transisi I-A. Papan lain memakai pita paling ketat.
- **Jangan pakai `"Watchlist"` untuk status.** Hanya 126 dari 198 emiten `"Watchlist"` yang bernotasi X di IDX (22 Sep 2026). `special_monitoring_board` hanya dari notasi X di `data/idx/notasi_khusus.csv`; kalau berkas tidak ada, statusnya `tidak_tersedia`.
- **Peraturan I-X yang berlaku (Kep-00035/BEI/06-2025) memakai 3 bulan**, bukan 6. Harga < Rp51 (III.1.1) bersifat kumulatif dengan likuiditas rendah; Papan Akselerasi dikecualikan dari kriteria harga (III.2); dividen tunai dalam 12 bulan membuat kriteria harga dan likuiditas `tidak_berlaku` (III.3).
- **Data IDX:** `idx.co.id` memblokir akses otomatis, tapi `idx.id` tidak. Notasi khusus diambil dari `https://www.idx.id/primary/ListedCompany/GetSpecialNotation?start=0&length=1000` lewat browser, lalu disimpan ke CSV beserta tanggal datanya. Huruf N dan I hanya menandai struktur hak suara, bukan masalah.
- Emiten keuangan: `altman_z`, `piotroski_f`, `accrual_ratio` berstatus `tidak_berlaku`, dan pilar 2 memakai varian bank.
- NPL tidak tersedia di Sectors. `allowance_for_loans / gross_loan` adalah proksi rasio pencadangan: labeli "proksi" dan jangan bandingkan dengan ambang NPL 5%.
- `cost_to_income_ratio` bukan BOPO. Jangan bandingkan dengan ambang 100%.
- Piotroski memakai data tahunan dari `historical_financials`, bukan kuartalan — semua fieldnya ada di sana, jadi tidak butuh panggilan kuartalan tambahan.
- Beneish M-Score tidak bisa dihitung: field piutang tidak ada di endpoint mana pun. Sudah dikeluarkan dari katalog dan diganti `accrual_ratio`. Jangan menghitung Beneish parsial — nilai potong −1,78 hanya sah untuk model 8 variabel penuh.

## Telegram

- `parse_mode="HTML"` dengan tag yang diizinkan saja. Teks yang perlu rata kolom harus di dalam `<pre>`.
- Maksimal 4.096 karakter per pesan. Pecah kartu di batas blok pilar, tidak di tengah kalimat.
- Laju pengiriman: ±1 pesan/detik per chat, ±30/detik total. Alert lewat antrean.
- Simpan `message_thread_id` per `(user_id, ticker)`. Kalau pembuatan topik atau pengiriman ke topik gagal, kirim ke chat utama. Bot tidak boleh berhenti karena topik.
- `/unregis` menutup topik, tidak menghapusnya.
- Hanya bot yang membuat topik. Izin pengguna membuat topik dimatikan di BotFather, jadi kode tidak perlu menangani topik buatan pengguna.
- `/risk` dan `/list` dijawab di chat utama. Alert dan kartu saham terdaftar dikirim ke topiknya.

## Penjadwalan

- Semua jadwal memakai zona `Asia/Jakarta` yang ditulis eksplisit. Server biasanya berjalan di UTC, dan 06.00 WIB adalah 23.00 UTC hari sebelumnya — jangan pernah mengandalkan zona waktu bawaan sistem.
- Putaran harian berjalan **Senin sampai Jumat** pukul 06.00. Jangan menjadwalkannya Sabtu dan Minggu: bursa tutup, tidak ada data baru. Putaran Senin yang melaporkan penutupan Jumat beserta peristiwa akhir pekan.
- Satu putaran mengerjakan semuanya: verifikasi data EOD, hitung ulang skor, kumpulkan peristiwa sejak putaran sebelumnya, lalu kirim **satu pesan per saham**. Jangan tambahkan jadwal baru tanpa memperbarui PRD bagian 12.
- Putaran dimulai dengan memverifikasi bahwa tanggal data EOD sudah maju sejak putaran sebelumnya. Kalau belum, hentikan tanpa mengirim apa pun. **Jangan membuat daftar hari libur bursa** — pengecekan ini sudah menanganinya sendiri.
- Simpan waktu putaran terakhir per pengguna di database, dan ambil peristiwa sejak waktu itu — bukan sejak 24 jam lalu — supaya tidak ada peristiwa yang terlewat atau terkirim dua kali saat putaran gagal.

## Rahasia dan jaringan

- Semua token dan kunci di `.env`; contohnya di `.env.example`. Jangan commit, jangan cetak ke log, jangan tulis di tes atau fixture.
- HTTPS memakai `certifi`. Dilarang mematikan verifikasi SSL, termasuk untuk debugging.

## AI

- Pakai klien **OpenAI-compatible** (`openai` Python SDK) lewat `chat.completions`. Semua koneksi dari env: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Jangan menulis nama provider atau URL di kode.
- **Jangan memakai fitur khusus satu vendor** — tool use, prompt caching, atau field respons di luar standar OpenAI. Provider harus bisa ditukar hanya dengan mengubah `.env`.
- `response_format={"type": "json_object"}` tidak didukung semua provider. Minta keluaran JSON lewat prompt, lalu parse defensif: buang pagar ```json, dan kalau parsing gagal jatuh ke kartu cadangan.
- Masukan satu-satunya adalah `indicators.json`; LLM tidak memanggil API apa pun.
- Prompt dirangkai dari `skills/analisis-risiko-saham/SKILL.md` dan `references/`. Istilah wajib memakai definisi dari `kamus-istilah.md`, supaya kalimat konsisten antar hari.
- Kalau LLM gagal, melewati batas waktu, atau keluarannya tidak bisa diparse, kirim kartu dari `render_fallback.py`. Jalur ini harus selalu berfungsi tanpa LLM.

## Tes

- Setiap indikator punya tes dengan fixture respons Sectors asli di `tests/fixtures/`, termasuk kasus null, emiten bank, dan papan akselerasi.
- `test_gate.py`: narasi yang memuat angka karangan harus ditolak.
- Tes determinisme: bangun `indicators.json` dua kali dari snapshot yang sama, hasilnya harus identik.
- Golden `tests/golden/indicators_*.json` dicocokkan byte per byte. Kalau perubahan disengaja, buat ulang golden lalu periksa diff-nya secara manual sebelum menyimpan.
- Tidak ada panggilan jaringan sungguhan di tes.

## Gaya kode

- Python 3.11+. Type hints wajib di fungsi publik.
- Nama variabel dan fungsi dalam bahasa Inggris. Teks yang dibaca pengguna dalam bahasa Indonesia.
- Konfigurasi ruff bawaan.
- **Komentar hanya untuk hal penting dan tidak terlihat dari kode**, maksimal 2 kalimat: alasan keputusan, jebakan data, atau risiko keamanan. Dilarang komentar yang mengulang isi kode, kode yang dikomentari, pembatas bagian, dan catatan riwayat perubahan. Kalau kodenya butuh komentar panjang supaya bisa dipahami, perbaiki nama atau strukturnya.
