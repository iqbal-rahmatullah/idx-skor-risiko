# PRD — Skor Risiko Saham

Bot Telegram · Sectors Financial API · Hackathon
Versi 1.0 · 22 September 2026 · Status: draf untuk disepakati tim

---

## 1. Ringkasan

Skor Risiko adalah fitur bot Telegram yang menilai risiko satu saham IDX dari 27 indikator dalam enam pilar, lalu menjelaskannya dalam bahasa yang dipahami investor pemula. Pengguna bisa bertanya kapan saja (`/risk`) atau mendaftarkan saham (`/regis`) supaya bot memberi tahu saat kondisinya berubah. Setiap saham yang didaftarkan punya topik sendiri di chat bot, tempat fitur berita dan skor risiko bertemu.

Kode menghitung semua angka. AI hanya menarasikan hasilnya.

## 2. Masalah

1. Investor pemula sering diajak membeli saham lewat grup WhatsApp atau Telegram, tanpa cara cepat menilai apakah ajakan itu masuk akal.
2. Screener yang ada menuntut pengguna tahu apa yang harus dicari. Tidak ada yang memberi tahu saat kondisi saham yang sudah dipegang berubah.
3. Angka tanpa konteks tidak berarti bagi pemula. "PBV 2,9" tidak menjawab pertanyaan "ini aman atau tidak".
4. Aplikasi yang menampilkan sinyal risiko jarang menunjukkan dasar ambangnya, sehingga tidak bisa diverifikasi.

## 3. Pengguna sasaran

Investor ritel pemula, usia 20–35, memegang 1–5 saham, belajar dari media sosial dan grup chat. Tidak paham istilah seperti free float atau kolektibilitas. Tidak membuka aplikasi analisis setiap hari. Butuh jawaban singkat untuk pertanyaan "saham ini bagaimana", dan butuh diberi tahu saat ada yang perlu diperhatikan.

## 4. Tujuan dan bukan-tujuan

| Tujuan | Bukan tujuan |
|---|---|
| Menilai risiko satu saham dengan metode yang bisa dijelaskan dan diverifikasi | Memberi rekomendasi beli atau jual |
| Memberi tahu pengguna saat kondisi saham yang dipantau berubah | Data real-time atau intraday |
| Menjelaskan setiap istilah untuk pemula | Membuktikan atau menuduh manipulasi pasar |
| Menampilkan yang baik, bukan hanya yang bermasalah | Menggantikan analisis fundamental menyeluruh |
| Setiap ambang punya sumber | Memprediksi harga |

## 5. Nilai pembeda

1. **Mendatangi pengguna.** Bot yang mengirim kabar saat ada perubahan, bukan menunggu ditanya.
2. **Membatalkan alarm palsu.** Bendera yang punya penjelasan wajar — pergerakan sesubsektor, tanggal ex-dividen, berita di rentang yang sama — ditandai tidak dihitung, beserta alasannya.
3. **Setiap angka punya kuitansi.** Ambang dari regulator disebut nomor peraturannya; yang tidak punya sumber resmi diakui dan diturunkan dari data.
4. **Dibuat untuk pemula.** Setiap poin menjelaskan metriknya dulu, baru angkanya.
5. **Satu topik per saham.** Riwayat lengkap satu saham, dari berita dan skor risiko, dalam satu tempat.

## 6. Posisi dalam produk tim

| Fitur | Pemilik | Membaca | Mengirim ke |
|---|---|---|---|
| Ringkasan berita | Developer A | snapshot bersama | topik saham |
| Skor risiko | [Anda] | snapshot bersama | topik saham, chat utama |

Kedua fitur membaca satu `TickerSnapshot` per ticker per hari. Tidak ada fitur yang memanggil Sectors API sendiri untuk data yang sudah ada di snapshot.

## 7. Fitur

### F1 — `/risk TICKER`

Sebagai pengguna, saya ingin mengetik kode saham dan mendapat penilaian risikonya, supaya bisa memutuskan apakah perlu mempelajarinya lebih lanjut.

- Ticker divalidasi terhadap daftar emiten lokal sebelum memanggil API. Ticker salah dijawab dengan saran ticker terdekat.
- Bot membalas tanda terima dalam 2 detik, lalu kartu lengkap menyusul.
- Jawaban muncul di chat utama, tidak membuat topik.
- Berlaku untuk saham apa pun, tidak harus didaftarkan.

### F2 — `/regis TICKER`

Sebagai pengguna, saya ingin mendaftarkan saham yang saya pegang, supaya diberi tahu saat kondisinya berubah.

- Membuat topik bernama sesuai ticker di chat pribadi dengan bot, lalu menyimpan `message_thread_id`.
- Kartu skor awal dikirim ke topik itu sebagai titik acuan.
- Kalau pembuatan topik gagal, saham tetap terdaftar dan semua pesan dikirim ke chat utama.
- Hanya bot yang membuat topik. Izin pengguna membuat topik sendiri dimatikan di pengaturan BotFather.

### F3 — `/list`

Menampilkan ringkasan semua saham yang dipantau: ticker, skor, grade, arah perubahan. Dibaca dari snapshot terakhir, tanpa panggilan API. Muncul di chat utama.

### F4 — `/unregis TICKER`

Menghentikan pemantauan dan **menutup** topik (bukan menghapus), supaya riwayatnya tetap bisa dibaca.

### F5 — Alert

Dikirim ke topik saham terkait pada putaran harian pukul 06.00 (Senin–Jumat), sebagai satu pesan yang memuat semua perubahan sejak putaran sebelumnya. Dikirim hanya bila salah satu terjadi:

- grade berpindah, atau skor bergeser 10 poin atau lebih;
- indikator bersumber regulator berubah jadi bermasalah (misalnya masuk Papan Pemantauan Khusus);
- peristiwa baru dari berita, filing, atau suspensi yang menyangkut saham itu.

Hari tanpa perubahan berarti topik diam.

## 8. Kebutuhan non-fungsional

| Kebutuhan | Target |
|---|---|
| Determinisme | Snapshot yang sama menghasilkan `indicators.json` yang identik, byte per byte |
| Ketertelusuran | Setiap angka di narasi cocok dengan field di `indicators.json`; yang tidak cocok dibuang |
| Waktu tanggap | Tanda terima < 2 detik; kartu lengkap < 45 detik |
| Degradasi | AI gagal → kartu cadangan tanpa narasi; topik gagal → chat utama; bot tidak pernah diam total |
| Batas Telegram | ≤ 4.096 karakter per pesan; ±1 pesan/detik per chat, ±30/detik total |
| Keamanan | Token di `.env`; verifikasi SSL selalu aktif; isi berita diperlakukan sebagai data, bukan instruksi |
| Kejujuran | Setiap kartu memuat tanggal data dan kalimat "bukan rekomendasi beli atau jual" |

## 9. Model penilaian

### Status indikator

| Status | Arti | Menaikkan skor? |
|---|---|---|
| `kuat` | jauh lebih baik dari ambang | tidak |
| `wajar` | memenuhi, tidak menonjol | tidak |
| `perhatian` | mendekati ambang | tidak (bobot nol) |
| `bermasalah` | melewati ambang | **ya** |
| `tidak_tersedia` | datanya null | dikeluarkan dari pembagi |
| `tidak_berlaku` | metrik tidak cocok untuk sektor ini | dikeluarkan dari pembagi |

### Perhitungan

```
skor_pilar = Σ bobot(bermasalah) / Σ bobot(indikator yang bisa dinilai) × 100
skor_akhir = rata-rata tertimbang skor_pilar
```

Indikator `tidak_tersedia` dan `tidak_berlaku` tidak masuk pembagi. Kalau dianggap nol, emiten dengan data paling sedikit justru terlihat paling aman.

Bobot awal indikator mengikuti kekuatan sumbernya: regulator 3, akademik 2, diturunkan dari data 1. Pengecualian dicatat di katalog. Bobot antar pilar awalnya sama; penyesuaian per sektor adalah keputusan tim dan harus didokumentasikan di `thresholds.py`.

### Grade

| Skor | Grade |
|---|---|
| 0–20 | A |
| 21–40 | B |
| 41–60 | C |
| 61–80 | D |
| 81–100 | E |

**Skor tinggi berarti risiko tinggi.** Kalimat ini wajib ada di setiap kartu.

### Pembatalan bendera

Pembatalan ditentukan **kode**, bukan AI, supaya tetap deterministik. Aturannya:

- pergerakan yang sama terjadi pada mayoritas emiten sesubsektor dalam jendela yang sama;
- tanggal ex-dividen atau aksi korporasi jatuh di jendela lonjakan;
- ada berita terkait saham itu di jendela yang sama.

Bendera yang dibatalkan masuk array `dismissed` beserta alasannya. AI hanya menjelaskannya.

## 10. Katalog 27 indikator

Kolom **Jenis**: R = regulator, A = akademik, D = diturunkan dari data.

### Pilar 1 — Ukuran dan likuiditas

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `free_float` | porsi saham beredar bebas | < 15% (Papan Akselerasi < 7,5%) | Peraturan BEI I-A, efektif 31 Mar 2026; Peraturan I-V | R | 3 |
| `daily_liquidity` | nilai dan volume transaksi rata-rata harian 6 bulan | nilai < Rp5 juta **dan** volume < 10.000 lembar | Peraturan BEI I-X, kriteria 7 | R | 3 |
| `sub_51_price` | harga rata-rata 6 bulan | < Rp51 | Peraturan BEI I-X, kriteria 1 | R | 3 |
| `volume_spike` | volume hari ini vs 90 hari saham itu | > persentil 95 | distribusi 90 hari saham itu | D | 1 |
| `broker_concentration` | porsi `net_idr` broker teratas terhadap total akumulasi | > persentil 95 riwayat saham itu | HHI hanya analogi (KPPU 1.800) | D | 1 |

### Pilar 2 — Kesehatan keuangan (non-keuangan)

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `negative_equity` | ekuitas | < 0 | Peraturan BEI I-X, kriteria 5 | R | 3 |
| `no_revenue` | pendapatan | nol, atau tidak berubah dari laporan sebelumnya | Peraturan BEI I-X, kriteria 3 | R | 3 |
| `debt_to_equity` | liabilitas terhadap ekuitas | > persentil 75 subsektor | field `debt_to_equity_ratio`; distribusi subsektor lewat screener | D | 1 |
| `altman_z` | risiko kebangkrutan 2 tahun | Z'' pasar berkembang < 1,1 | Altman (1968) dan turunannya | A | 2 |
| `piotroski_f` | 9 cek akuntansi | skor ≤ 2 | Piotroski (2000); dihitung dari `historical_financials` tahunan | A | 2 |

### Pilar 2 — varian bank

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `car` | modal terhadap aset tertimbang risiko | < 8% (batas terendah, profil risiko 1) | POJK 11/POJK.03/2016 jo. POJK 27/POJK.03/2022 | R | 3 |
| `npl_proxy` | `abs(allowance_for_loans) / gross_loan` | > persentil 75 bank lain | proksi; definisi NPL di POJK 40/2019 | D | 1 |
| `ldr_rim` | kredit terhadap dana | di luar 84–94% | PADG 21/5/PADG/2019 dan perubahannya | R | 2 |
| `cost_to_income` | efisiensi (proksi BOPO) | > persentil 75 bank lain | proksi, bukan BOPO | D | 1 |
| `nim` | selisih bunga | < persentil 25 bank lain | distribusi bank | D | 1 |

Untuk emiten keuangan, `altman_z`, `piotroski_f`, dan `accrual_ratio` berstatus `tidak_berlaku`.

### Pilar 3 — Valuasi

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `pe_vs_peer` | PER terhadap rata-rata sejenis | `pe` > `pe_peer_avg` (PER ≤ 0 → `tidak_berlaku`) | field Sectors; PER 15 Graham hanya rujukan | D | 1 |
| `pb_vs_peer` | PBV terhadap rata-rata sejenis | `pb` > `pb_peer_avg` | field Sectors | D | 1 |
| `graham_number` | harga terhadap √(22,5 × EPS × BVPS) | harga > Graham Number; butuh EPS dan BVPS positif | Graham, *The Intelligent Investor* bab 14 | A | 2 |

### Pilar 4 — Kepemilikan dan orang dalam

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `insider_selling` | penjualan direksi, komisaris, pemegang ≥ 5% | ada penjualan dalam 30 hari | POJK 4/2024; sinyal lemah menurut Lakonishok & Lee (2001) | A | 1 |
| `insider_buying` | pembelian orang dalam | — (hanya status `kuat`, tidak masuk skor) | Lakonishok & Lee (2001) | A | 0 |
| `shareholder_concentration` | porsi pemegang saham terbesar | > ambang yang dikalibrasi ke daftar HSC BEI | proksi HSC; metodologi indeks BEI 2026 | D | 1 |
| `retail_share_shift` | perubahan porsi ritel antar kuartal | kenaikan > persentil 90 | `individual_l + individual_f` terhadap `total_l + total_f` | D | 1 |

### Pilar 5 — Perilaku harga

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `ara_arb_frequency` | berapa kali menyentuh batas harian dalam 10 hari | > persentil 95 subsektor | batas: SK Kep-00003/BEI/04-2025; frekuensi dari return `/daily` | D | 1 |
| `volatility_90d` | RSD harga 90 hari | > persentil 90 subsektor | distribusi subsektor dari `/daily` | D | 1 |
| `drawdown_90d` | penurunan terdalam dari puncak | > persentil 90 subsektor | distribusi subsektor dari `/daily` | D | 1 |
| `unexplained_move` | lonjakan harga tanpa katalis | return harian > persentil 95 saham itu dan tidak ada berita atau aksi korporasi di jendela | return dari `/daily`; aturan pembatalan di bagian 9 | D | 2 |

### Pilar 6 — Peristiwa dan berita

| ID | Mengukur | Bermasalah bila | Sumber | Jenis | Bobot |
|---|---|---|---|---|---|
| `special_notation` | notasi khusus BEI | ada notasi bermasalah | pengumuman BEI; E, D, A, S dihapus 30 Nov 2026, notasi P baru | R | 3 |
| `special_monitoring_board` | status Papan Pemantauan Khusus | notasi X | Peraturan BEI I-X | R | 3 |
| `suspension_uma` | suspensi atau UMA | ada dalam 90 hari | Peraturan BEI II-A; kriteria UMA tidak dipublikasikan | R | 2 |
| `negative_news` | berita bertag Bearish atau Violation | ≥ 3 dalam 7 hari (pilihan tim) | tag `/news` Sectors | D | 1 |
| `dilution_event` | right issue atau warrant | ada dalam 90 hari | `/company/corporate-actions` | D | 2 |
| `accrual_ratio` | selisih laba dan arus kas operasi terhadap aset | > persentil 75 subsektor | Sloan (1996), *The Accounting Review* 71(3) | A | 1 |

Total: 5 + 5 + 3 + 4 + 4 + 6 = **27**. Indikator baru wajib ditambahkan di tabel ini dulu, lengkap dengan sumbernya.

## 10b. Catatan verifikasi API (22 September 2026)

Diuji langsung dengan 24 panggilan memakai ANTM (non-keuangan), BBCA (bank), dan AEGS (Papan Akselerasi). Respons mentah tersimpan di `tests/fixtures/`.

- Autentikasi: header `Authorization: <key>` **tanpa** `Bearer`. Varian `Bearer` ditolak 401.
- `/v1` sudah dimatikan (410). Semua panggilan lewat `/v2`.
- `listing_board` bernilai `"Main"` (260 emiten), `"Development"` (457), `"Watchlist"` (198, Papan Pemantauan Khusus), `"Acceleration"` (44), `"New Economy"` (3). `"Watchlist"` tidak selalu sinkron dengan IDX, jadi hanya sinyal pendukung.
- `/daily` dibatasi **90 hari kalender**, bukan 90 hari bursa: hasilnya 63 baris. Rentang lebih panjang dipotong diam-diam tanpa error. Likuiditas 6 bulan karena itu butuh 2–3 panggilan untuk backfill awal.
- `top-changes` maksimal 10 emiten. Tidak bisa dipakai sebagai cakupan pasar.
- Field piutang dan depresiasi tidak tersedia di data kuartalan maupun tahunan, sehingga Beneish M-Score tidak bisa dihitung dan dikeluarkan dari katalog.
- `efficiency_ratio` bernilai sama persis dengan `roa` — kemungkinan bug data, jangan dipakai.
- Komposisi pemegang saham dilaporkan **bulanan**, bukan kuartalan.
- Screener menolak `order_by=-pe`; yang benar `order_by=-pe[2025]&include_query_values=true`.
- Aritmetika di `where` dan `order_by` berfungsi dan nilai hitungannya ikut dikembalikan. Satu panggilan mengembalikan CAR, LDR, cost-to-income, NIM, dan proksi NPL untuk 46 dari 48 bank; nilai BBCA cocok dengan `/company/report`. Ini menggantikan puluhan panggilan per emiten.
- Kunci di `query_values` sama persis dengan teks ekspresinya: lewat `order_by` tanpa spasi, lewat `where` dengan spasi.
- Null di `order_by` ikut kembali dan ditaruh di akhir (13 dari 114 emiten untuk DER). Null di `where` justru membuat barisnya hilang (95 dari 114; bank 46 dari 48).
- `debt_to_equity_ratio` dihitung sebagai total liabilitas ÷ ekuitas, bukan `total_debt / total_equity` (ANTM: 0,435 versus 0,119).
- `allowance_for_loans` bernilai negatif, sehingga proksi NPL harus memakai nilai absolutnya.
- Kredit terbaca dari header `limit-consumption`: report 1 per section, broker-summary 2, quarterly 1 per kuartal, top-changes 1. Endpoint lain belum mengirim header itu.

**Konsekuensi arsitektur.** `/daily` diperlakukan sebagai alat backfill, bukan sumber kebenaran. Deret harga disimpan dan ditambah setiap putaran hari bursa, sehingga setelah sebulan berjalan riwayat 6 bulan tersedia lokal tanpa panggilan berulang, dan distribusi subsektor dihitung dari data yang sudah terkumpul.

## 11. Kontrak data

### `TickerSnapshot`

Satu per ticker per tanggal, disimpan di database, dibaca kedua fitur.

```
symbol, as_of, sector, sub_sector, listing_board
overview      market_cap, free_float, tags, indices
price         deret close/volume 90 hari (urut naik), splits
financials    tahunan dan kuartalan, rasio bank
valuation     pe, pb, peer_avg, intrinsic_value
ownership     pemegang saham, komposisi, filings insider
broker        top_buyers, top_sellers
events        news, suspensions, corporate_actions
idx_lists     notasi khusus, papan pemantauan, HSC
sources       [{endpoint, fetched_at}]
```

### `indicators.json`

Satu-satunya masukan ke AI. Contoh satu indikator:

```json
{
  "id": "free_float",
  "pillar": "ukuran_likuiditas",
  "label": "Free float",
  "status": "bermasalah",
  "is_new": false,
  "since": "2026-09-02",
  "value": 0.14,
  "display": "14%",
  "threshold": "15%",
  "source": "Peraturan BEI No. I-A",
  "source_type": "regulator",
  "weight": 3,
  "evidence_path": "ownership.free_float"
}
```

Tingkat atas memuat `symbol`, `as_of`, `trigger`, `score`, `summary_counts`, `pillars[]`, `dismissed[]`, `unavailable[]`, dan `context` (berita dan aksi korporasi di jendela, pergerakan subsektor, harga komoditas).

`display` selalu diformat kode. AI tidak pernah mengubah desimal jadi persen sendiri.

## 12. Alur sistem

```
Pemicu → snapshot → mesin aturan → indicators.json → AI + skill → gerbang angka → Telegram
```

### Jadwal (WIB)

| Waktu | Pekerjaan |
|---|---|
| 06.00, Senin–Jumat | Putaran harian tunggal: pastikan tanggal data EOD sudah maju sejak putaran sebelumnya, hitung ulang skor, kumpulkan berita, filing, dan suspensi sejak putaran sebelumnya, cek kuartal baru, lalu kirim **satu pesan per saham** ke topiknya bila ada perubahan |
| Senin 05.00 | Distribusi **subsektor** untuk ambang persentil. Rasio fundamental dan rasio bank: satu panggilan screener beraritmetika per subsektor (1 kredit). Volatilitas, drawdown, dan frekuensi ARA/ARB: `/daily` untuk **semua** anggota subsektor, sampai 90 hari bursa tersimpan lokal untuk semua emiten yang pernah didaftarkan pengguna lewat `/regis`. Perbarui juga daftar IDX (notasi khusus, papan pemantauan, HSC) |

Alasan memilih 06.00: pasar tutup dari 16.00 sampai 09.00, sehingga alert sore maupun pagi sama-sama baru bisa ditindaklanjuti saat pembukaan. Pukul 06.00 memberi pengguna waktu membaca sebelum pasar buka, dan pada jam itu data EOD hari sebelumnya sudah pasti tersedia sehingga tidak perlu polling berulang sejak sore.

Alasan Senin–Jumat: bursa tutup akhir pekan, jadi putaran Sabtu dan Minggu tidak akan menemukan data baru. Putaran Senin melaporkan penutupan Jumat beserta berita dan filing yang terbit selama akhir pekan, dan pengguna masih bisa menindaklanjutinya saat pembukaan Senin pukul 09.00. Menjalankannya Sabtu justru lebih buruk: isinya sama, tapi pengguna harus menunggu dua hari untuk bisa bertindak.

**Hari libur bursa tidak perlu didaftarkan.** Putaran selalu dimulai dengan membandingkan tanggal data EOD terhadap putaran sebelumnya. Kalau belum maju, putaran berhenti tanpa mengirim apa pun. Libur nasional karena itu tertangani sendiri: putaran setelah libur menemukan data yang sama dan diam, lalu putaran berikutnya menemukan data baru dan mengirim.

Tidak ada putaran tambahan di jam bursa. Peristiwa mendesak seperti suspensi atau notasi khusus baru juga menunggu putaran 06.00.

Putaran tunggal ini juga yang menggabungkan keluaran fitur berita dan skor risiko menjadi satu pesan per saham, sehingga topik tidak kebanjiran notifikasi.

### Narasi dan cadangan

1. Kode membangun `indicators.json`.
2. Bot mengirim tanda terima.
3. AI menulis narasi dengan skill.
4. Gerbang angka membuang kalimat yang angkanya tak terlacak.
5. Kartu dikirim. Kalau AI gagal atau melewati batas waktu, kartu cadangan tanpa narasi dikirim.

## 13. Output

Urutan blok kartu tetap: judul (membawa pemicu bila alert), skor dan grade dengan arah perubahan, satu kalimat ringkasan, hitungan status, lalu enam pilar dengan vonis dan seluruh indikatornya — masing-masing dengan penjelasan untuk pemula — kemudian bendera yang dibatalkan, indikator tak terdata, dan kuitansi.

Kartu lengkap sekitar 6.000 karakter. Di topik saham, kartu dipecah dua pesan di batas pilar. Alert memakai versi ringkas: indikator bermasalah, dua yang terkuat, dan hitungan status.

## 14. Metrik keberhasilan

- 27 indikator menghasilkan status untuk minimal 20 emiten uji, termasuk 3 bank.
- Tes determinisme lulus untuk semua emiten uji.
- Gerbang menolak 100% angka karangan di tes.
- Setiap ambang di katalog punya sumber yang bisa dibuka.
- Demo menampilkan dua momen: satu alert dengan alasan kuat, satu bendera yang dibatalkan beserta penjelasannya.
- Demo bisa diputar tanpa internet dari snapshot tersimpan.

## 15. Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Topik di chat pribadi rusak lagi (pernah terjadi setelah Bot API 10.0) | Jalur cadangan ke chat utama selalu ada |
| Notasi E, D, A, S dihapus BEI 30 Nov 2026 | Proksi dari data keuangan tetap dihitung; daftar notasi diambil dari sumber, tidak di-hardcode |
| BEI merevisi kriteria Papan Pemantauan Khusus | Kriteria disimpan di `thresholds.py` dengan tanggal berlaku |
| Syarat penggunaan situs IDX soal pengambilan data | Periksa sebelum scrape; cadangan: salin manual daftar mingguan ke CSV |
| Banyak field Sectors bernilai null | Status `tidak_tersedia`, pilar ditandai parsial |
| AI lambat atau gagal | Tanda terima + kartu cadangan |
| Isi berita memuat instruksi tersembunyi | Isi berita dibungkus sebagai data, gerbang angka tetap berlaku |
| Python di Mac gagal verifikasi SSL | `certifi` wajib di dependensi |
| Dua fitur membanjiri satu topik | Satu pesan gabungan per saham per putaran |

## 16. Keputusan tim (23 September 2026)

Semua pertanyaan terbuka sudah dijawab:

1. Status `perhatian` berbobot nol, tidak menaikkan skor.
2. Tidak ada putaran tambahan di jam bursa. Semua peristiwa menunggu putaran 06.00.
3. Distribusi persentil memakai semua anggota subsektor, tanpa batas jumlah.
4. Pengguna dilarang membuat topik sendiri. Izinnya dimatikan di BotFather, dan hanya bot yang membuat topik.
5. Thesis Watcher di luar lingkup dokumen ini.
6. `/daily` per anggota subsektor dihentikan setelah 90 hari bursa tersimpan lokal untuk semua emiten yang pernah didaftarkan lewat `/regis`.

## 17. Teknologi

| Lapisan | Pilihan | Alasan |
|---|---|---|
| Bahasa | Python 3.11+ | numpy untuk persentil dan MAD; ekosistem data kuat |
| Bot Telegram | python-telegram-bot v21+ | async, JobQueue bawaan untuk jadwal; bila method topik terbaru belum didukung, panggil Bot API langsung lewat httpx |
| HTTP | httpx + certifi | async; `certifi` mencegah gagal SSL di Mac |
| Komputasi | numpy | persentil, MAD, cummax |
| Database | SQLite + SQLAlchemy 2.x | satu file, cukup untuk hackathon; mudah dipindah ke Postgres |
| Penjadwal | JobQueue python-telegram-bot | tidak perlu cron terpisah |
| LLM | Klien **OpenAI-compatible** (`openai` Python SDK) dengan `base_url`, kunci, dan model dari env | satu antarmuka untuk OpenAI, OpenRouter, Groq, Together, atau model lokal (vLLM, Ollama); provider bisa ditukar tanpa ubah kode |
| Skill | folder `skills/analisis-risiko-saham/` format Agent Skills | isinya dirangkai ke system prompt; bisa dipakai juga dari Claude Code |
| Scraping IDX | httpx + selectolax | cek dulu endpoint JSON internal lewat tab Network |
| Konfigurasi | pydantic-settings + `.env` | rahasia di luar kode |
| Tes | pytest + fixture JSON | respons Sectors nyata tersimpan, tanpa panggilan API |
| Kualitas kode | ruff | lint dan format satu alat |
| Deploy | Docker, satu kontainer, long polling | tidak butuh domain atau webhook |

## 18. Fase pengerjaan

Setiap fase punya kriteria keluar. Fase berikutnya dimulai setelah kriteria terpenuhi.

### Fase 0 — Fondasi

- Repo, `CLAUDE.md`, PRD ini, `.env.example`, ruff, pytest.
- Klien Sectors dengan certifi.
- Skema `TickerSnapshot` dan `indicators.json` disepakati bersama Developer A dan B.
- Tes topik di chat pribadi (sudah berhasil).

**Keluar:** `python -m bot` membalas `/start`; satu snapshot ANTM tersimpan di database.

### Fase 1 — Mesin aturan inti

- Indikator bersumber regulator: `free_float`, `daily_liquidity`, `sub_51_price`, `negative_equity`, `no_revenue`, `special_notation`, `special_monitoring_board`, `suspension_uma`, dan varian bank `car`, `ldr_rim`.
- Status, skor pilar, skor akhir, grade, `build_json`.
- Tes fixture untuk tiap indikator dan tes determinisme.

**Keluar:** `indicators.json` untuk ANTM dan BBCA benar dan lulus tes.

### Fase 2 — Bot dan kartu cadangan

- `/risk`, `/regis`, `/list`, `/unregis`.
- Topik per saham dengan jalur cadangan ke chat utama.
- Kartu cadangan tanpa AI.

**Keluar:** pengguna bisa mendaftarkan 3 saham, mendapat 3 topik, dan menerima kartu cadangan di masing-masing.

### Fase 3 — Narasi AI

- Skill: `SKILL.md`, kamus istilah, aturan nada, cara membaca kombinasi, contoh narasi.
- Perangkai prompt, pemanggil LLM, gerbang angka.
- Alur tanda terima → kartu → cadangan.

**Keluar:** tes gerbang menolak angka karangan; kartu AI jadi untuk 5 emiten uji.

### Fase 4 — Pemantauan

- Putaran harian 06.00 WIB Senin–Jumat dan putaran mingguan Senin 05.00, zona `Asia/Jakarta` eksplisit.
- Pembanding snapshot dan aturan alert F5.
- Aturan pembatalan bendera.
- Integrasi fitur berita (Developer A) ke topik saham.

**Keluar:** alert masuk ke topik yang benar saat fixture berubah; tidak ada pesan saat tidak ada perubahan.

### Fase 5 — Indikator lanjutan dan demo

- `altman_z`, `piotroski_f`, `accrual_ratio`, `graham_number`.
- Semua indikator berbasis persentil dari distribusi pasar.
- Mode demo dari snapshot tersimpan.
- Verifikasi ulang seluruh nomor peraturan dan tautan sumber.

**Keluar:** 27 indikator berjalan; demo dua momen bisa diputar tanpa internet.

---

## Lampiran — sumber

Periksa ulang seluruh tautan sebelum presentasi; beberapa aturan berubah antara 2024 dan 2026.

- Peraturan BEI I-X (Papan Pemantauan Khusus): https://www.idx.id/Media/pyuil405/signed_peraturan_i_x_penempatan_pencatatan_ebe_pada_papan_pemantauan_khusus.pdf
- Daftar efek pemantauan khusus: https://www.idx.co.id/id/perusahaan-tercatat/daftar-efek-pemantauan-khusus/
- Daftar notasi khusus: https://www.idx.co.id/id/perusahaan-tercatat/notasi-khusus/
- Free float 15%: https://market.bisnis.com/read/20260401/7/1963525/bei-resmi-berlakukan-free-float-15-big-caps-diberi-tenggat-waktu-hingga-2027
- ARA/ARB (Kep-00003/BEI/04-2025): https://www.cnbcindonesia.com/market/20250408084106-17-624101/bei-ubah-kebijakan-arb-ini-aturan-terbarunya
- Metodologi indeks dan HSC: https://www.idx.co.id/media/3lvd1yk1/lampiran-panduan-metodologi-indeks-idx80-lq45-dan-idx30.pdf
- POJK 11/POJK.03/2016 (KPMM): https://peraturan.bpk.go.id/Download/135028/POJK%20Nomor%2011%20Tahun%202016.pdf
- POJK 40/POJK.03/2019 (kualitas aset): https://www.ojk.go.id/id/regulasi/Documents/Pages/Penilaian-Kualitas-Aset-Bank-Umum/pojk%2040-2019.pdf
- PBI 23/2/PBI/2021 (syarat NPL < 5%): https://www.bi.go.id/id/publikasi/peraturan/Pages/PBI_230221.aspx
- FAQ PADG 21/5/PADG/2019 (RIM 84–94%): https://www.bi.go.id/id/publikasi/peraturan/Documents/FAQ_PADG_210519.pdf
- POJK 4 Tahun 2024 (laporan kepemilikan): https://peraturan.bpk.go.id/Download/344501/peraturan-ojk-no-4-tahun-2024.pdf
- Pedoman merger KPPU (HHI): https://www.kppu.go.id/docs/Merger/Lampiran.pdf
- Lakonishok & Lee (2001), DOI 10.1093/rfs/14.1.79: https://ideas.repec.org/a/oup/rfinst/v14y2001i1p79-111.html
- Piotroski (2000): http://www.chicagobooth.edu/~/media/FE874EE65F624AAEBD0166B1974FD74D.pdf
- Sloan (1996), *The Accounting Review* 71(3), 289–315 — anomali akrual: https://ideas.repec.org/a/inm/ormnsc/v57y2011i5p797-816.html (Green, Hand & Soliman 2011 mencatat efeknya meluruh di pasar AS)
- Altman Z-Score: https://en.wikipedia.org/wiki/Altman_Z-score
- Graham Number: https://stablebread.com/graham-number/
- Sectors API: https://docs.sectors.app/get-started/v2/overview