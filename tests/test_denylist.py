from apptutorial.privacy.denylist import is_denied

DENY = ("1password.exe", "keepass.exe")


def test_denied_is_case_insensitive():
    assert is_denied("1Password.exe", DENY)
    assert is_denied("KEEPASS.EXE", DENY)


def test_allowed_processes_not_denied():
    assert not is_denied("excel.exe", DENY)
    assert not is_denied("", DENY)
    assert not is_denied("notepad.exe", ())
