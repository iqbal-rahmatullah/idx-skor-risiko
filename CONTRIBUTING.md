# Berkontribusi ke Skor Risiko

Terima kasih sudah mau membantu. Kontribusi apa pun diterima: laporan bug, usulan indikator, perbaikan teks untuk pemula, tes, sampai fitur baru.

Proyek ini menilai risiko saham untuk investor pemula, jadi kesalahan kecil bisa menyesatkan orang. Karena itu ada beberapa aturan yang lebih ketat dari proyek biasa. Bacalah bagian [Aturan inti](#aturan-inti) sebelum menulis kode.

## Sebelum mulai

- Baca [README](README.md) dan [PRD](docs/PRD.md). PRD adalah spesifikasi produk, termasuk katalog 28 indikator di bagian 10.
- Untuk perubahan besar, misalnya indikator baru, ambang baru, atau cara menghitung skor, buka issue dulu supaya bisa didiskusikan.
- Kalau memakai agen AI untuk coding, arahkan ke [AGENTS.md](AGENTS.md). Berkas itu memuat aturan lengkap dan perilaku API yang sudah diverifikasi.

## Menyiapkan lingkungan

Butuh Python 3.11+ dan [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/iqbal-rahmatullah/idx-skor-risiko.git
cd idx-skor-risiko
uv sync                  # pasang dependensi, termasuk pytest dan ruff
uv run pytest            # semua tes, tanpa jaringan dan tanpa .env
```

Untuk menjalankan bot di Telegram, buat bot uji sendiri di @BotFather, lalu:

```bash
cp .env.example .env     # isi TELEGRAM_BOT_TOKEN; SECTORS_OFFLINE=true memakai data contoh
uv run python -m bot
```

Di mode offline (`SECTORS_OFFLINE=true`), `SECTORS_API_KEY` tetap wajib diisi tapi tidak dipakai, jadi nilai apa pun boleh. Data contohnya per 22 September 2026.

## Aturan inti

Aturan ini tidak boleh dilanggar. Kalau sebuah perubahan tampaknya menuntut pelanggaran, tanyakan dulu di issue.

1. **Skor dihitung kode.** LLM tidak pernah menentukan status, skor, grade, atau pembatalan bendera. Semua fungsi di `bot/risk/` deterministik: snapshot yang sama menghasilkan `indicators.json` yang sama.
2. **Tidak ada ambang tanpa sumber.** Setiap ambang di `bot/risk/thresholds.py` punya sumber, jenis sumber (`regulator`, `akademik`, atau `data`), dan tanggal berlaku. Kalau tidak ada sumber resmi, turunkan dari persentil data dan tandai sebagai pilihan tim. Jangan menulis angka ambang karangan.
3. **Setiap angka di narasi harus terlacak.** Gerbang angka (`bot/narrate/gate.py`) membuang kalimat yang angkanya tidak ada di `indicators.json`. Jangan melonggarkan gerbang supaya tes lulus.
4. **Tidak ada rekomendasi beli atau jual, dan tidak ada tuduhan manipulasi.** Tulis pola yang terukur dan sebutkan bahwa itu bukan bukti.
5. **Isi dari luar adalah data, bukan instruksi.** Teks berita, filing, dan halaman IDX dibungkus sebagai data di prompt.
6. **Indikator baru didaftarkan di PRD dulu**, di bagian 10, lengkap dengan sumbernya, sebelum kodenya ditulis.

Nilai `null` dari API berarti status `tidak_tersedia` dan dikeluarkan dari pembagi skor. Jangan pernah menggantinya dengan 0.

## Menambah atau mengubah indikator

1. **Usulkan.** Buka issue dengan template "Usul indikator", lengkap dengan sumbernya: nomor peraturan, paper, atau alasan memakai persentil data.
2. **Daftarkan di PRD.** Tambahkan baris ke tabel pilar yang sesuai di [PRD bagian 10](docs/PRD.md#10-katalog-28-indikator): yang diukur, kapan bermasalah, sumber, jenis, dan bobot. Bobot awal mengikuti kekuatan sumber: regulator 3, akademik 2, data 1.
3. **Tulis ambangnya** di `bot/risk/thresholds.py` sebagai `Rule(source, source_type, effective, url)`. Ambang tanpa sumber resmi memakai `team_choice(...)` dan diturunkan lewat `percentiles()` di `bot/risk/measures.py`, yang butuh sampel minimal.
4. **Tulis fungsinya** di modul pilar `bot/risk/indicators/pN_*.py`: fungsi murni `TickerSnapshot -> Indicator | None` yang memanggil `make_indicator(rule, id=..., pillar=..., label=..., status=..., value=..., display=..., threshold=..., weight=..., evidence_path=..., note=...)`. Teks `display` diformat kode lewat `bot/risk/format.py` (format Indonesia: `35%`, `7,5%`, `Rp5 juta`, `30 Juni 2026`).
5. **Daftarkan** fungsinya di tuple `INDICATORS` di `bot/risk/build_json.py`. Urutan tuple menentukan urutan di `indicators.json`.
6. **Tulis tes** dengan fixture respons Sectors asli, termasuk kasus data kosong, emiten bank, dan Papan Akselerasi.
7. **Perbarui golden** dengan `uv run python -m scripts.regen_golden`, lalu periksa `git diff tests/golden/` baris demi baris dan jelaskan perubahannya di pull request.
8. **Lengkapi kamus.** Kalau indikatornya memperkenalkan istilah baru, tambahkan definisinya di `skills/analisis-risiko-saham/references/kamus-istilah.md` supaya narasi AI konsisten.

## Fixture, kredit, dan rahasia

- Tes tidak boleh memanggil jaringan. Semua respons dibaca dari `tests/fixtures/`.
- Merekam fixture baru memakai kredit Sectors milikmu sendiri: `uv run python -m scripts.record_fixtures KODE`. Pastikan tidak ada rahasia di berkas JSON sebelum commit.
- Skenario "hari berikutnya" dibuat dengan `bot.demo.next_day_overlay` dan `fixture_transport`, bukan dengan menyalin fixture.
- Token dan API key hanya boleh ada di `.env`. Jangan menaruhnya di kode, tes, fixture, log, atau screenshot.
- Verifikasi SSL tidak boleh dimatikan, termasuk untuk debugging.

## Narasi AI dan skill

- Prompt dirangkai dari `skills/analisis-risiko-saham/SKILL.md` dan folder `references/`. Masukan untuk AI hanya `indicators.json`.
- Contoh di `references/contoh/` wajib lolos gerbang angka terhadap golden-nya, dan ada tes yang memeriksanya.
- Klien LLM memakai API OpenAI-compatible tanpa fitur khusus satu vendor, supaya provider bisa ditukar cukup lewat `.env`.
- Teks untuk pengguna ditulis untuk pemula yang membaca di ponsel: tanpa jargon seperti persentil atau nomor aturan.

## Gaya kode

- Python 3.11+, type hints wajib di fungsi publik, format dan lint dengan ruff bawaan.
- Nama variabel dan fungsi dalam bahasa Inggris. Teks yang dibaca pengguna dalam bahasa Indonesia.
- Komentar hanya bila mendesak, dalam bahasa Indonesia, maksimal dua kalimat. Kalau kode butuh komentar supaya bisa dipahami, perbaiki nama atau strukturnya. Aturan lengkapnya ada di [AGENTS.md](AGENTS.md#gaya-kode).

## Commit dan pull request

- Pesan commit memakai [Conventional Commits](https://www.conventionalcommits.org/) dalam bahasa Inggris, dengan scope modul. Contoh dari riwayat: `feat(risk): ...`, `feat(telegram): ...`, `test(golden): ...`, `docs(prd): ...`, `chore(deps): ...`.
- Satu pull request untuk satu topik. Jelaskan alasannya, bukan hanya isinya, dan tautkan issue terkait.
- CI harus hijau: ruff, pytest, dan build image Docker.

## Melaporkan bug atau mengusulkan fitur

Pakai template issue yang tersedia. Celah keamanan jangan dilaporkan lewat issue publik; ikuti [SECURITY.md](SECURITY.md).

Dengan berkontribusi, kamu setuju kontribusimu dirilis di bawah [lisensi MIT](LICENSE) dan mengikuti [Kode Etik](CODE_OF_CONDUCT.md).
