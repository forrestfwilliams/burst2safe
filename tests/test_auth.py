from pathlib import Path

from burst2safe import auth


def test_get_netrc(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(auth, 'system', lambda: 'Windows')
        assert auth.get_netrc() == Path.home() / '_netrc'

    with monkeypatch.context() as m:
        m.setattr(auth, 'system', lambda: 'Linux')
        assert auth.get_netrc() == Path.home() / '.netrc'


def test_find_creds_in_env(monkeypatch):
    with monkeypatch.context() as m:
        m.setenv('TEST_USERNAME', 'foo')
        m.setenv('TEST_PASSWORD', 'bar')
        assert auth.find_creds_in_env('TEST_USERNAME', 'TEST_PASSWORD') == ('foo', 'bar')

    with monkeypatch.context() as m:
        m.delenv('TEST_USERNAME', raising=False)
        m.delenv('TEST_PASSWORD', raising=False)
        assert auth.find_creds_in_env('TEST_USERNAME', 'TEST_PASSWORD') == (None, None)


def test_find_creds_in_netrc(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(auth, 'get_netrc', lambda: tmp_path / '.netrc')
        (tmp_path / '.netrc').write_text('machine test login foo password bar')
        assert auth.find_creds_in_netrc('test') == ('foo', 'bar')

    with monkeypatch.context() as m:
        m.setattr(auth, 'get_netrc', lambda: tmp_path / '.netrc')
        (tmp_path / '.netrc').write_text('')
        assert auth.find_creds_in_netrc('test') == (None, None)
