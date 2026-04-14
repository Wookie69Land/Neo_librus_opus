from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.api.jwt_utils import decode_token, encode_token
from app.domain.models import Author, Book, Library, LibraryBook, LibraryUser, SessionToken, Voivodeship


class BookAvailabilityApiTests(TestCase):
    def setUp(self) -> None:
        self.user = LibraryUser.objects.create_user(
            username="reader",
            email="reader@example.com",
            password="secret123",
            region=Voivodeship.MAZOWIECKIE,
        )
        self.session = SessionToken.objects.create(key="test-token", user=self.user)
        self.book = Book.objects.create(title="Pan Tadeusz", isbn="9780306406157")

        self.other_library = Library.objects.create(
            name="Biblioteka Gdansk",
            city="Gdansk",
            region=Voivodeship.POMORSKIE,
        )
        self.local_library = Library.objects.create(
            name="Biblioteka Warszawa",
            city="Warszawa",
            region=Voivodeship.MAZOWIECKIE,
        )

        self.other_library_book = LibraryBook.objects.create(
            book=self.book,
            library=self.other_library,
            is_available=False,
        )
        self.local_library_book = LibraryBook.objects.create(
            book=self.book,
            library=self.local_library,
            is_available=True,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.session.key}"}

    def test_book_availability_endpoint_uses_mock_check_and_prioritizes_user_region(self) -> None:
        response = self.client.get(f"/api/books/{self.book.id}/availability", **self._auth_headers())

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["book_id"], self.book.id)
        self.assertEqual(payload["checked_via"], "mock-library-api")
        self.assertEqual(payload["user_region"], Voivodeship.MAZOWIECKIE)
        self.assertEqual(payload["libraries"][0]["name"], "Biblioteka Warszawa")
        self.assertTrue(payload["libraries"][0]["is_available"])
        self.assertEqual(payload["libraries"][0]["availability_source"], "mock-library-api")
        self.assertIn("availability_checked_at", payload["libraries"][0])

    def test_recent_book_update_keeps_current_model_availability_value(self) -> None:
        Book.objects.filter(id=self.book.id).update(last_updated=timezone.now() - timedelta(minutes=2))

        with patch("app.api.book_availability.random.random", return_value=0.99):
            response = self.client.get(
                f"/api/books/{self.book.id}/availability",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["libraries"][0]["is_available"])
        self.assertFalse(payload["libraries"][1]["is_available"])

    def test_stale_book_update_uses_mocked_75_25_distribution(self) -> None:
        Book.objects.filter(id=self.book.id).update(last_updated=timezone.now() - timedelta(minutes=6))

        with patch("app.api.book_availability.random.random", side_effect=[0.80, 0.20]):
            response = self.client.get(
                f"/api/books/{self.book.id}/availability",
                **self._auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["libraries"][0]["is_available"])
        self.assertTrue(payload["libraries"][1]["is_available"])

        self.local_library_book.refresh_from_db()
        self.other_library_book.refresh_from_db()
        self.assertFalse(self.local_library_book.is_available)
        self.assertTrue(self.other_library_book.is_available)

    def test_get_book_returns_libraries_sorted_for_authenticated_user_region(self) -> None:
        response = self.client.get(f"/api/books/{self.book.id}", **self._auth_headers())

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["id"], self.book.id)
        self.assertEqual(payload["libraries"][0]["name"], "Biblioteka Warszawa")
        self.assertEqual(payload["libraries"][1]["name"], "Biblioteka Gdansk")

    def test_search_books_returns_libraries_sorted_for_authenticated_user_region(self) -> None:
        response = self.client.get("/api/search/books", {"q": "Pan"}, **self._auth_headers())

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["items"][0]["id"], self.book.id)
        self.assertEqual(payload["items"][0]["libraries"][0]["name"], "Biblioteka Warszawa")
        self.assertEqual(payload["items"][0]["libraries"][1]["name"], "Biblioteka Gdansk")


class AdvancedBookSearchApiTests(TestCase):
    def setUp(self) -> None:
        self.user = LibraryUser.objects.create_user(
            username="searcher",
            email="searcher@example.com",
            password="secret123",
            region=Voivodeship.MAZOWIECKIE,
        )
        self.session = SessionToken.objects.create(key="advanced-search-token", user=self.user)

        self.author_mickiewicz = Author.objects.create(name="Adam Mickiewicz")
        self.author_gombrowicz = Author.objects.create(name="Witold Gombrowicz")
        self.author_slowacki = Author.objects.create(name="Juliusz Slowacki")

        self.book_polish = Book.objects.create(title="Pan Tadeusz", isbn="9780306406157", language="pol")
        self.book_polish.authors.add(self.author_mickiewicz)

        self.book_english = Book.objects.create(title="Ferdydurke", isbn="9783161484100", language="eng")
        self.book_english.authors.add(self.author_gombrowicz)

        self.book_german = Book.objects.create(title="Kordian", isbn="9780140449136", language="de")
        self.book_german.authors.add(self.author_slowacki)

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.session.key}"}

    def test_advanced_search_supports_multiple_languages_and_author_names(self) -> None:
        response = self.client.get(
            "/api/search/books/advanced",
            {
                "languages": ["eng", "pol"],
                "author_names": ["Adam Mickiewicz", "Witold Gombrowicz"],
            },
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual({item["title"] for item in payload["items"]}, {"Pan Tadeusz", "Ferdydurke"})

    def test_advanced_search_supports_multiple_author_ids(self) -> None:
        response = self.client.get(
            "/api/search/books/advanced",
            {"author_ids": [self.author_mickiewicz.id, self.author_gombrowicz.id]},
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual({item["title"] for item in payload["items"]}, {"Pan Tadeusz", "Ferdydurke"})

    def test_advanced_search_paginates_results(self) -> None:
        response = self.client.get(
            "/api/search/books/advanced",
            {"page": 2, "page_size": 1},
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["page_size"], 1)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["total_pages"], 3)
        self.assertEqual(len(payload["items"]), 1)


class UserUpdateApiTests(TestCase):
    def setUp(self) -> None:
        self.user = LibraryUser.objects.create_user(
            username="updater",
            email="updater@example.com",
            password="Secret123!Pass",
            first_name="Jan",
            last_name="Kowalski",
            region=Voivodeship.MAZOWIECKIE,
        )
        self.token = encode_token(
            {
                "sub": str(self.user.id),
                "username": self.user.username,
                "email": self.user.email,
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "region": self.user.region,
                "date_joined": self.user.date_joined.isoformat(),
                "role_id": 0,
                "library_id": 0,
                "jti": "initial-session",
            }
        )
        self.session = SessionToken.objects.create(key=self.token, user=self.user)

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_update_user_returns_refreshed_token_for_self_update(self) -> None:
        response = self.client.put(
            f"/api/users/{self.user.id}",
            data={"email": "updated@example.com", "first_name": "Anna", "region": Voivodeship.POMORSKIE},
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("token", payload)
        self.assertNotEqual(payload["token"], self.token)
        self.assertEqual(payload["user"]["email"], "updated@example.com")
        self.assertEqual(payload["user"]["first_name"], "Anna")
        self.assertEqual(payload["user"]["region"], Voivodeship.POMORSKIE)

        refreshed_claims = decode_token(payload["token"])
        self.assertEqual(refreshed_claims["email"], "updated@example.com")
        self.assertEqual(refreshed_claims["first_name"], "Anna")
        self.assertEqual(refreshed_claims["region"], Voivodeship.POMORSKIE)

        self.session.refresh_from_db()
        self.assertEqual(self.session.key, payload["token"])