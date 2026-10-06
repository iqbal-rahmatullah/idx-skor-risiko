# Kebijakan keamanan

## Melaporkan celah keamanan

Jangan membuka issue publik untuk celah keamanan. Laporkan secara privat lewat fitur **Report a vulnerability** di tab [Security](https://github.com/iqbal-rahmatullah/idx-skor-risiko/security) repositori ini.

Sertakan:

- jenis masalah dan dampaknya;
- langkah untuk mereproduksi, atau bukti konsep yang aman;
- versi atau commit yang terdampak.

Maintainer akan membalas secepat mungkin dan memberi tahu perkembangannya sampai perbaikan dirilis. Mohon beri waktu untuk memperbaiki sebelum detailnya dipublikasikan.

## Versi yang didukung

Hanya cabang `main` yang menerima perbaikan keamanan.

## Yang termasuk lingkup

- Bocornya token Telegram, API key Sectors, atau API key LLM, misalnya lewat log, pesan error, fixture, atau image Docker.
- Instruksi tersembunyi di isi berita atau filing yang bisa membuat narasi AI keluar dari aturan, misalnya memberi ajakan beli atau jual.
- Cara melewati gerbang angka sehingga angka karangan atau tautan sampai ke pengguna.
- Cara menghabiskan kredit Sectors milik pemasang bot di luar penggunaan normal.

## Yang di luar lingkup

- Bot belum punya daftar izin pengguna dan pembatas laju. Ini batasan yang sudah diketahui dan didokumentasikan; pemasang diminta membagikan bot hanya ke orang yang dipercaya.
- Kerentanan pada layanan pihak ketiga (Telegram, Sectors, penyedia LLM). Laporkan langsung ke pihak terkait.

## Praktik untuk pemasang

- Simpan semua rahasia hanya di `.env`, dan jangan pernah meng-commit berkas itu.
- Jangan mematikan verifikasi sertifikat HTTPS.
- Jalankan satu proses bot untuk satu token.
- Ganti token di @BotFather bila ada dugaan token bocor.
