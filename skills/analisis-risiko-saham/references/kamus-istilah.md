# Kamus istilah

Definisi baku untuk setiap indikator, status, dan istilah. Narasi AI dan hasil tanpa AI memakai kalimat yang sama supaya penjelasan konsisten antar hari. Format baris `- \`id\` — definisi` dibaca oleh kode; jangan diubah.

## Indikator

- `free_float` — Porsi saham yang beredar bebas di publik, bukan dipegang pengendali. Makin kecil porsinya, makin mudah harga digerakkan segelintir pihak.
- `daily_liquidity` — Rata-rata nilai dan jumlah lembar yang diperdagangkan per hari selama 3 bulan. Saham yang sepi transaksi sulit dijual saat Anda membutuhkannya.
- `sub_51_price` — Rata-rata harga penutupan 3 bulan. BEI menandai saham di bawah Rp51 yang juga sepi transaksi.
- `volume_spike` — Jumlah lembar yang diperdagangkan hari ini dibanding kebiasaan saham itu sendiri dalam 90 hari terakhir.
- `broker_concentration` — Seberapa besar pembelian bersih hari ini menumpuk di satu perusahaan sekuritas, dibanding kebiasaan saham itu.
- `relative_liquidity` — Nilai transaksi harian dibanding saham lain di subsektor yang sama. Menandai saham yang jauh lebih sepi daripada rekan sejenisnya.
- `negative_equity` — Ekuitas negatif berarti total utang lebih besar dari total aset; modal pemilik sudah habis.
- `no_revenue` — Perusahaan tidak mencatat pendapatan usaha, atau pendapatannya sama persis dengan laporan sebelumnya.
- `debt_to_equity` — Total liabilitas dibanding modal sendiri, dibandingkan dengan perusahaan sejenis.
- `altman_z` — Skor Altman menggabungkan empat rasio neraca untuk memperkirakan risiko kesulitan keuangan dalam dua tahun.
- `piotroski_f` — Sembilan pemeriksaan sederhana atas laporan keuangan tahunan. Skornya 0 sampai 9; makin tinggi makin sehat.
- `car` — Modal bank dibanding aset berisikonya; bantalan untuk menyerap kerugian bila kredit macet.
- `npl_proxy` — Cadangan kerugian kredit dibanding total kredit bank. Ini proksi, bukan NPL resmi, karena NPL tidak tersedia di data.
- `ldr_rim` — Kredit yang disalurkan bank dibanding dana nasabahnya. Terlalu tinggi berarti likuiditas bank ketat.
- `cost_to_income` — Biaya operasional bank dibanding pendapatannya. Proksi efisiensi, bukan BOPO resmi.
- `nim` — Selisih bunga yang diterima dan dibayar bank, dibanding aset yang menghasilkan bunga.
- `pe_vs_peer` — PER adalah harga saham dibagi laba per saham, dibanding rata-rata perusahaan sejenis. PER lebih tinggi berarti Anda membayar lebih mahal untuk tiap rupiah laba.
- `pb_vs_peer` — PBV adalah harga saham dibagi nilai buku per saham, dibanding rata-rata perusahaan sejenis.
- `graham_number` — Batas harga wajar versi Benjamin Graham, dihitung dari laba dan nilai buku per saham.
- `insider_selling` — Direksi, komisaris, atau pemegang 5% ke atas menjual saham dalam 30 hari terakhir. Sinyalnya lemah, karena penjualan bisa terjadi untuk kebutuhan pribadi.
- `insider_buying` — Orang dalam membeli saham dalam 30 hari terakhir. Ini informasi positif dan tidak menambah skor risiko.
- `shareholder_concentration` — BEI mengumumkan kepemilikan saham ini sangat terkonsentrasi pada segelintir pihak (Kepemilikan Saham Terkonsentrasi Tinggi).
- `retail_share_shift` — Perubahan porsi investor individu bulan terakhir dibanding saham lain di subsektor. Porsi ritel yang melonjak bisa berarti pemegang besar sedang melepas saham ke ritel.
- `ara_arb_frequency` — Berapa kali harga menyentuh batas naik harian (ARA) atau batas turun harian (ARB) dalam 10 hari bursa terakhir.
- `volatility_90d` — Seberapa liar harga bergoyang dalam 90 hari, dibanding saham sejenis.
- `drawdown_90d` — Penurunan terdalam dari harga puncak dalam 90 hari, dibanding saham sejenis.
- `unexplained_move` — Kenaikan harga hari ini jauh di atas kebiasaan saham itu. Menjadi bendera bila tidak ada berita, aksi korporasi, atau pergerakan subsektor yang menjelaskannya.
- `special_notation` — Huruf yang ditempel BEI di kode saham untuk menandai kondisi tertentu, misalnya E untuk ekuitas negatif atau L untuk laporan keuangan yang terlambat.
- `special_monitoring_board` — Papan Pemantauan Khusus: saham diperdagangkan lewat lelang berkala karena memenuhi salah satu kriteria BEI.
- `suspension_uma` — BEI menghentikan sementara perdagangan saham ini dalam 90 hari terakhir.
- `negative_news` — Jumlah berita bernada negatif atau tentang pelanggaran terkait saham ini dalam 7 hari terakhir.
- `dilution_event` — Right issue atau waran dalam 90 hari. Jumlah saham bisa bertambah dan porsi Anda mengecil bila tidak ikut.
- `accrual_ratio` — Selisih antara laba yang dilaporkan dan kas yang benar-benar masuk, dibanding aset. Laba yang jauh di atas kas perlu dicek lebih lanjut.

## Status

- `kuat` — Jauh lebih baik dari ambang.
- `wajar` — Memenuhi ambang, tidak menonjol.
- `perhatian` — Mendekati ambang; belum dihitung sebagai masalah.
- `bermasalah` — Melewati ambang dan menaikkan skor risiko.
- `tidak_tersedia` — Datanya tidak ada, jadi tidak ikut dihitung.
- `tidak_berlaku` — Ukuran ini tidak cocok untuk emiten ini, jadi tidak ikut dihitung.

## Istilah

- `skor` — Angka 0–100 dari bobot indikator yang bermasalah. Skor tinggi berarti risiko tinggi.
- `grade` — Huruf A sampai E dari skor: A untuk 0–20, B 21–40, C 41–60, D 61–80, E 81–100.
- `persentil` — Posisi dibanding kelompoknya. Di atas persentil 90 subsektor berarti lebih tinggi dari 90% saham sejenis.
- `subsektor` — Kelompok perusahaan dengan bidang usaha yang sama menurut klasifikasi BEI.
- `dibatalkan` — Bendera yang punya penjelasan wajar, misalnya berita atau pergerakan seluruh subsektor, sehingga tidak dihitung.
