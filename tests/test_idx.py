from datetime import date

from bot.idx.lists import idx_lists_for


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


def test_loader_missing_notation_file_leaves_notations_unknown(tmp_path):
    assert idx_lists_for("ANTM", tmp_path / "tidak-ada.csv").notations is None


def test_real_csv_has_inps_on_monitoring_board():
    lists = idx_lists_for("INPS")

    assert "X" in lists.notations


def write_hsc(path, rows):
    header = "kode,peristiwa,tanggal,tanggal_data,sumber_url,keterangan\n"
    path.write_text(header + "".join(f"{r}\n" for r in rows))


def test_hsc_membership_follows_latest_event(tmp_path):
    hsc = tmp_path / "hsc.csv"
    write_hsc(
        hsc,
        [
            "LUCY,pengenaan,2026-04-02,2026-09-23,https://idx.id/a.pdf,x",
            "LUCY,pencabutan,2026-07-02,2026-09-23,https://idx.id/b.pdf,x",
            "NICK,pengenaan,2026-09-22,2026-09-23,https://idx.id/c.pdf,x",
        ],
    )
    notations = tmp_path / "tidak-ada.csv"

    assert idx_lists_for("NICK", notations, hsc).hsc is True
    assert idx_lists_for("LUCY", notations, hsc).hsc is False
    assert idx_lists_for("ANTM", notations, hsc).hsc is False
    assert idx_lists_for("ANTM", notations, hsc).notations is None
    assert idx_lists_for("NICK", notations, hsc).hsc_as_of == date(2026, 9, 23)


def test_both_files_missing_is_none(tmp_path):
    assert idx_lists_for("ANTM", tmp_path / "a.csv", tmp_path / "b.csv") is None


def test_real_hsc_list():
    assert idx_lists_for("NICK").hsc is True
    assert idx_lists_for("LUCY").hsc is False
    assert idx_lists_for("ANTM").hsc is False
