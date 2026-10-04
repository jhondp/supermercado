from pathlib import Path

from supermercado.orchestrator.serve import serve_directory


def test_serve_directory_binds_localhost_and_stops(tmp_path: Path) -> None:
    url, stop = serve_directory(tmp_path)
    try:
        assert url.startswith("http://127.0.0.1:")
        assert int(url.rsplit(":", 1)[1].rstrip("/")) > 0
    finally:
        stop()
