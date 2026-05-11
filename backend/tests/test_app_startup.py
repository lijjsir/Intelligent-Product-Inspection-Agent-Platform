def test_backend_app_imports():
    from main import app

    assert app.title == "PIAP Backend"
