import io

from config.runtime import configure_utf8_output


def test_utf8_output_handles_pipeline_language_arrows():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")

    configure_utf8_output(stream)
    stream.write("English → Cebuano\n")
    stream.flush()

    assert raw.getvalue().decode("utf-8").replace("\r\n", "\n") == "English → Cebuano\n"
