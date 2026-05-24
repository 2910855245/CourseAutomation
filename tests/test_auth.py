"""Tests for authentication: JWT, password hashing, permissions."""


class TestPasswordHashing:
    def test_hash_and_verify(self):
        from api.auth import hash_password, verify_password
        pw = "my_secure_password"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True

    def test_wrong_password_fails(self):
        from api.auth import hash_password, verify_password
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self):
        from api.auth import hash_password
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTToken:
    def test_create_and_verify(self):
        from api.auth import create_token, verify_token
        token = create_token("user123", "admin", "admin")
        payload = verify_token(token)
        assert payload is not None
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"

    def test_expired_token_rejected(self):
        import jwt

        from api.auth import verify_token
        from config import settings

        # Create an already-expired token
        expired_payload = {"sub": "admin", "username": "admin", "role": "admin", "exp": 1000000000}
        token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm="HS256")

        result = verify_token(token)
        assert result is None  # expired tokens return None

    def test_invalid_token_rejected(self):
        from api.auth import verify_token
        result = verify_token("invalid.token.here")
        assert result is None

    def test_token_blacklist(self):
        from api.auth import blacklist_token, create_token, is_token_blacklisted
        token = create_token("user1", "admin", "admin")
        assert is_token_blacklisted(token) is False
        blacklist_token(token)
        assert is_token_blacklisted(token) is True


class TestLoginEndpoint:
    def test_unauthorized_access_rejected(self, client):
        resp = client.get("/api/admin/dashboard")
        assert resp.status_code in (401, 403)

    def test_invalid_token_rejected(self, client):
        resp = client.get(
            "/api/admin/dashboard",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code in (401, 403)
