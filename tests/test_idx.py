from datetime import date

from bot.idx.lists import NOTATION_CSV, idx_lists_for


def write_csv(path, rows):
    header = "kode,notasi,tanggal_data,sumber_url,keterangan\n"
    path.write_text(header + "".join(f"{r}\n" for r in rows))


def test_loader_reads_notations_and_date(tmp_path):
    csv = tmp_path / "notasi.csv"
    write_csv(csv, ['ABCD,"E,X",2026-09-22,https://idx.id/x,"E : ekuitas negatif"'])

    lists = idx_lists_for("ABCD", csv)

    assert lists.notations == ["E", "X"]
    assert lists.as_of == date(2026, 9, 22)
    assert lists.source_url == "https://idx.id/x"


def test_loader_symbol_absent_means_no_notation(tmp_path):
    csv = tmp_path / "notasi.csv"
    write_csv(csv, ['ABCD,"E,X",2026-09-22,https://idx.id/x,""'])

    lists = idx_lists_for("ANTM", csv)

    assert lists.notations == []
    assert lists.as_of == date(2026, 9, 22)


def test_loader_missing_file_is_none(tmp_path):
    assert idx_lists_for("ANTM", tmp_path / "tidak-ada.csv") is None


def test_real_csv_has_inps_on_monitoring_board():
    lists = idx_lists_for("INPS", NOTATION_CSV)

    assert "X" in lists.notations
