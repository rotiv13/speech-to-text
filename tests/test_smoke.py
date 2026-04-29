def test_package_imports():
    import speech_to_text
    assert speech_to_text.__version__


def test_cli_main_callable():
    from speech_to_text.cli import main
    assert callable(main)
