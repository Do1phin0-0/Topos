from topos.config import _normalize_database_url


def test_render_style_postgres_url_is_normalized():
    # Render and Heroku hand out postgres://, which SQLAlchemy 2.0 rejects.
    assert _normalize_database_url(
        "postgres://user:pw@host.oregon-postgres.render.com/db"
    ) == "postgresql://user:pw@host.oregon-postgres.render.com/db"


def test_already_valid_urls_are_left_alone():
    url = "postgresql://topos:topos@localhost:5432/topos"
    assert _normalize_database_url(url) == url


def test_password_containing_the_scheme_text_is_not_mangled():
    url = "postgresql://u:postgres://weird@localhost/db"
    assert _normalize_database_url(url) == url
