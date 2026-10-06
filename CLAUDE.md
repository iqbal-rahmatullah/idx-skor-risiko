# Skor Risiko — aturan proyek untuk Claude Code

@AGENTS.md

Spesifikasi produk, katalog 28 indikator, dan keputusan tim:

@docs/PRD.md

## Khusus Claude Code

- Aturan yang berlaku untuk semua agen ditulis di `AGENTS.md`, bukan di berkas ini. Berkas ini hanya untuk hal yang khusus Claude Code.
- Sebelum menyatakan pekerjaan selesai, jalankan pemeriksaan yang sama dengan CI: `uv run ruff check .`, `uv run ruff format --check .`, dan `uv run pytest`.
