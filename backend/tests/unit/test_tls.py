import ssl

import httpx

from yimmparking.interface.container import build_http_client, relaxed_tls_context


def test_relaxed_context_still_verifies_but_skips_the_strict_x509_profile() -> None:
    context = relaxed_tls_context()
    # Chain and host name checking stay on...
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    # ...only the strict profile (which rejects data.ntpc.gov.tw's certificate) is off.
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT


def test_only_the_new_taipei_host_gets_the_relaxed_transport() -> None:
    client = build_http_client("test")
    try:
        default = client._transport  # noqa: SLF001
        relaxed = client._transport_for_url(httpx.URL("https://data.ntpc.gov.tw/api/x"))  # noqa: SLF001
        assert relaxed is not default
        for url in (
            "https://tcgbusfs.blob.core.windows.net/x",
            "https://maps.googleapis.com/x",
            "https://data.ntpc.gov.tw.evil.example/x",
            "https://evil.example/data.ntpc.gov.tw",
        ):
            assert client._transport_for_url(httpx.URL(url)) is default, url  # noqa: SLF001
    finally:
        client.close()
