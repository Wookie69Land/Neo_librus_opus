from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.api.jwt_utils import decode_token, encode_token
from app.domain.models import (
    Author,
    Book,
    Library,
    LibraryAdmin,
    LibraryBook,
    LibraryUser,
    Reservation,
    Role,
    SessionToken,
    Status,
    Voivodeship,
)


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


class ReservationApiTests(TestCase):
    def setUp(self) -> None:
        self.user = LibraryUser.objects.create_user(
            username="reserver",
            email="reserver@example.com",
            password="secret123",
            region=Voivodeship.MAZOWIECKIE,
        )
        self.session = SessionToken.objects.create(key="reservation-token", user=self.user)
        self.book = Book.objects.create(title="Solaris", isbn="9780306406157")
        self.library = Library.objects.create(name="Biblioteka Centralna", city="Warszawa")
        self.library_book = LibraryBook.objects.create(book=self.book, library=self.library, is_available=True)

        self.other_library = Library.objects.create(name="Biblioteka Pomocnicza", city="Lodz")
        self.other_library_book = LibraryBook.objects.create(
            book=self.book,
            library=self.other_library,
            is_available=True,
        )

        self.role = Role.objects.create(name="library admin test")
        self.library_admin_user = LibraryUser.objects.create_user(
            username="libraryadmin",
            email="libraryadmin@example.com",
            password="secret123",
        )
        self.library_admin_session = SessionToken.objects.create(
            key="library-admin-token",
            user=self.library_admin_user,
        )
        LibraryAdmin.objects.create(
            library=self.library,
            user=self.library_admin_user,
            role=self.role,
        )

        self.other_admin_user = LibraryUser.objects.create_user(
            username="otheradmin",
            email="otheradmin@example.com",
            password="secret123",
        )
        self.other_admin_session = SessionToken.objects.create(
            key="other-admin-token",
            user=self.other_admin_user,
        )
        LibraryAdmin.objects.create(
            library=self.other_library,
            user=self.other_admin_user,
            role=self.role,
        )

        self.other_reader_user = LibraryUser.objects.create_user(
            username="otherreader",
            email="otherreader@example.com",
            password="secret123",
        )
        self.other_reader_session = SessionToken.objects.create(
            key="other-reader-token",
            user=self.other_reader_user,
        )

        self.no_reservations_user = LibraryUser.objects.create_user(
            username="emptyreader",
            email="emptyreader@example.com",
            password="secret123",
        )
        self.no_reservations_session = SessionToken.objects.create(
            key="empty-reader-token",
            user=self.no_reservations_user,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.session.key}"}

    def _auth_headers_for(self, session: SessionToken) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {session.key}"}

    def _library_admin_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.library_admin_session.key}"}

    def _other_admin_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.other_admin_session.key}"}

    def _create_reservation(
        self,
        session: SessionToken | None = None,
        library_id: int | None = None,
        book_id: int | None = None,
    ) -> dict:
        auth_session = session or self.session
        response = self.client.post(
            "/api/reservations",
            data={
                "library_id": library_id or self.library.id,
                "book_id": book_id or self.book.id,
            },
            content_type="application/json",
            **self._auth_headers_for(auth_session),
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_create_reservation_assigns_default_pending_status(self) -> None:
        payload = self._create_reservation()
        self.assertEqual(payload["reader"]["id"], self.user.id)
        self.assertEqual(payload["status"]["name"], "pending")
        self.assertTrue(Status.objects.filter(name="pending").exists())

    def test_create_reservation_requires_book_in_selected_library(self) -> None:
        self.library_book.delete()

        response = self.client.post(
            "/api/reservations",
            data={"library_id": self.library.id, "book_id": self.book.id},
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Book is not available in the selected library")

    def test_create_reservation_returns_not_found_when_book_does_not_exist(self) -> None:
        response = self.client.post(
            "/api/reservations",
            data={"library_id": self.library.id, "book_id": 111111111},
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Book not found")

    def test_create_reservation_returns_not_found_when_library_does_not_exist(self) -> None:
        response = self.client.post(
            "/api/reservations",
            data={"library_id": 987654321, "book_id": self.book.id},
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Library not found")

    def test_only_matching_library_admin_can_accept_reservation(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="accepted")
        accepted_status = Status.objects.get(name="accepted")

        forbidden_response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._other_admin_headers(),
        )
        self.assertEqual(forbidden_response.status_code, 403)

        allowed_response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(allowed_response.json()["status"]["name"], "accepted")

    def test_admin_can_reject_pending_reservation(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="rejected")
        rejected_status = Status.objects.get(name="rejected")

        response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": rejected_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"]["name"], "rejected")

    def test_admin_cannot_transition_accepted_reservation(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="accepted")
        accepted_status = Status.objects.get(name="accepted")
        Status.objects.get_or_create(name="closed")
        closed_status = Status.objects.get(name="closed")

        # accept first
        self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )

        # try to move again — not allowed from accepted
        response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": closed_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid reservation status transition")

    def test_user_can_cancel_pending_reservation(self) -> None:
        payload = self._create_reservation()
        response = self.client.delete(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)

        get_response = self.client.get(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers(),
        )
        self.assertEqual(get_response.json()["status"]["name"], "cancelled")

    def test_user_can_cancel_accepted_reservation(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="accepted")
        accepted_status = Status.objects.get(name="accepted")

        self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )

        response = self.client.delete(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)

        get_response = self.client.get(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers(),
        )
        self.assertEqual(get_response.json()["status"]["name"], "cancelled")

    def test_user_cannot_cancel_rejected_reservation(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="rejected")
        rejected_status = Status.objects.get(name="rejected")

        self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": rejected_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )

        response = self.client.delete(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Cannot cancel", response.json()["detail"])

    def test_user_cannot_cancel_closed_reservation(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="closed")
        closed_status = Status.objects.get(name="closed")
        Reservation.objects.filter(id=payload["id"]).update(status=closed_status)

        response = self.client.delete(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Cannot cancel", response.json()["detail"])

    def test_non_owner_cannot_cancel_reservation(self) -> None:
        payload = self._create_reservation()
        response = self.client.delete(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers_for(self.other_reader_session),
        )
        self.assertEqual(response.status_code, 403)

    def test_list_reservations_returns_only_current_user_reservations_for_non_admin(self) -> None:
        own_reservation = self._create_reservation(session=self.session)
        self._create_reservation(session=self.other_reader_session)

        response = self.client.get("/api/reservations", **self._auth_headers())
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], own_reservation["id"])
        self.assertEqual(payload["items"][0]["reader"]["id"], self.user.id)

    def test_list_reservations_returns_only_admin_library_reservations_for_admin(self) -> None:
        self._create_reservation(session=self.session, library_id=self.library.id)
        self._create_reservation(
            session=self.other_reader_session,
            library_id=self.other_library.id,
        )

        response = self.client.get("/api/reservations", **self._library_admin_headers())
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["library"]["id"], self.library.id)

    def test_list_reservations_returns_empty_list_when_no_related_reservations(self) -> None:
        response = self.client.get(
            "/api/reservations",
            **self._auth_headers_for(self.no_reservations_session),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_list_reservations_pagination_structure(self) -> None:
        self._create_reservation()

        response = self.client.get("/api/reservations", **self._auth_headers())
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        for key in ("items", "page", "page_size", "total", "total_pages"):
            self.assertIn(key, payload)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["total_pages"], 1)

    def test_list_reservations_pagination_limits_items(self) -> None:
        self._create_reservation(session=self.session)
        self._create_reservation(session=self.session)
        self._create_reservation(session=self.session)

        response = self.client.get(
            "/api/reservations", {"page": 1, "page_size": 2}, **self._auth_headers()
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["total_pages"], 2)
        self.assertEqual(payload["page_size"], 2)

    def test_list_reservations_filter_by_status(self) -> None:
        pending = self._create_reservation()
        Status.objects.get_or_create(name="rejected")
        rejected_status = Status.objects.get(name="rejected")
        Reservation.objects.filter(id=pending["id"]).update(status=rejected_status)

        self._create_reservation()  # second reservation, stays pending

        response = self.client.get(
            "/api/reservations", {"status": "pending"}, **self._auth_headers()
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["status"]["name"], "pending")

    def test_list_reservations_admin_filter_by_library_id(self) -> None:
        self._create_reservation(session=self.session, library_id=self.library.id)
        self._create_reservation(session=self.other_reader_session, library_id=self.other_library.id)

        response = self.client.get(
            "/api/reservations",
            {"library_id": self.library.id},
            **self._library_admin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["library"]["id"], self.library.id)

    def test_list_reservations_admin_filter_by_unmanaged_library_returns_empty(self) -> None:
        # Library admin of self.library requests reservations for a library they don't manage.
        # Before the fix the filter was silently ignored and returned the admin's own library
        # reservations; after the fix an empty list is returned.
        self._create_reservation(session=self.session, library_id=self.library.id)
        self._create_reservation(session=self.other_reader_session, library_id=self.other_library.id)

        response = self.client.get(
            "/api/reservations",
            {"library_id": self.other_library.id},
            **self._library_admin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["items"], [])

    def test_reservation_response_includes_state_active_for_pending(self) -> None:
        payload = self._create_reservation()
        self.assertEqual(payload["state"], "active")

    def test_reservation_response_includes_state_active_for_accepted(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="accepted")
        accepted_status = Status.objects.get(name="accepted")

        response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        self.assertEqual(response.json()["state"], "active")

    def test_reservation_response_includes_state_completed_for_closed(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="closed")
        closed_status = Status.objects.get(name="closed")
        Reservation.objects.filter(id=payload["id"]).update(status=closed_status)

        response = self.client.get(f"/api/reservations/{payload['id']}", **self._auth_headers())
        self.assertEqual(response.json()["state"], "completed")

    def test_reservation_response_includes_state_unfulfilled_for_cancelled(self) -> None:
        payload = self._create_reservation()
        self.client.delete(f"/api/reservations/{payload['id']}", **self._auth_headers())

        response = self.client.get(f"/api/reservations/{payload['id']}", **self._auth_headers())
        self.assertEqual(response.json()["state"], "unfulfilled")

    def test_reservation_response_includes_state_unfulfilled_for_rejected(self) -> None:
        payload = self._create_reservation()
        Status.objects.get_or_create(name="rejected")
        rejected_status = Status.objects.get(name="rejected")
        Reservation.objects.filter(id=payload["id"]).update(status=rejected_status)

        response = self.client.get(f"/api/reservations/{payload['id']}", **self._auth_headers())
        self.assertEqual(response.json()["state"], "unfulfilled")

    def test_reservation_planned_end_time_approximately_48h_for_pending(self) -> None:
        from datetime import datetime as dt, timezone as utctz

        payload = self._create_reservation()
        self.assertIsNotNone(payload["planned_end_time"])

        planned = dt.fromisoformat(payload["planned_end_time"])
        expected = dt.now(tz=utctz.utc) + timedelta(hours=48)
        delta_seconds = abs((planned - expected).total_seconds())
        self.assertLess(delta_seconds, 10)

    def test_reservation_planned_end_time_approximately_3_days_for_accepted(self) -> None:
        from datetime import datetime as dt, timezone as utctz

        payload = self._create_reservation()
        Status.objects.get_or_create(name="accepted")
        accepted_status = Status.objects.get(name="accepted")

        response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        accepted = response.json()
        self.assertIsNotNone(accepted["planned_end_time"])

        planned = dt.fromisoformat(accepted["planned_end_time"])
        expected = dt.now(tz=utctz.utc) + timedelta(days=3)
        delta_seconds = abs((planned - expected).total_seconds())
        self.assertLess(delta_seconds, 10)

    def test_reservation_planned_end_time_is_none_after_cancellation(self) -> None:
        payload = self._create_reservation()
        self.client.delete(f"/api/reservations/{payload['id']}", **self._auth_headers())

        response = self.client.get(f"/api/reservations/{payload['id']}", **self._auth_headers())
        self.assertIsNone(response.json()["planned_end_time"])

    def test_cancel_reservation_sets_end_time(self) -> None:
        payload = self._create_reservation()
        self.assertIsNone(payload["end_time"])

        self.client.delete(f"/api/reservations/{payload['id']}", **self._auth_headers())

        response = self.client.get(f"/api/reservations/{payload['id']}", **self._auth_headers())
        self.assertIsNotNone(response.json()["end_time"])

    # ------------------------------------------------------------------
    # Coverage gap tests
    # ------------------------------------------------------------------

    def test_superuser_can_list_all_reservations(self) -> None:
        superuser = LibraryUser.objects.create_superuser(
            username="superadmin",
            email="superadmin@example.com",
            password="super123",
        )
        superuser_session = SessionToken.objects.create(key="superadmin-token", user=superuser)
        self._create_reservation(session=self.session)
        self._create_reservation(session=self.other_reader_session)

        response = self.client.get(
            "/api/reservations",
            **self._auth_headers_for(superuser_session),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 2)

    def test_superuser_can_filter_by_library_id(self) -> None:
        superuser = LibraryUser.objects.create_superuser(
            username="superadmin2",
            email="superadmin2@example.com",
            password="super123",
        )
        superuser_session = SessionToken.objects.create(key="superadmin2-token", user=superuser)
        self._create_reservation(session=self.session, library_id=self.library.id)
        self._create_reservation(session=self.other_reader_session, library_id=self.other_library.id)

        response = self.client.get(
            "/api/reservations",
            {"library_id": self.library.id},
            **self._auth_headers_for(superuser_session),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["library"]["id"], self.library.id)

    def test_regular_user_list_with_library_id_filter(self) -> None:
        self._create_reservation(session=self.session, library_id=self.library.id)
        self._create_reservation(session=self.session, library_id=self.other_library.id)

        response = self.client.get(
            "/api/reservations",
            {"library_id": self.library.id},
            **self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["library"]["id"], self.library.id)

    def test_get_nonexistent_reservation_returns_404(self) -> None:
        response = self.client.get("/api/reservations/999999", **self._auth_headers())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Reservation not found")

    def test_get_reservation_forbidden_for_unrelated_user(self) -> None:
        payload = self._create_reservation(session=self.session)
        response = self.client.get(
            f"/api/reservations/{payload['id']}",
            **self._auth_headers_for(self.other_reader_session),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Permission denied")

    def test_update_nonexistent_reservation_returns_404(self) -> None:
        accepted_status, _ = Status.objects.get_or_create(name="accepted")
        response = self.client.put(
            "/api/reservations/999999",
            data={"status_id": accepted_status.id},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Reservation not found")

    def test_update_reservation_with_nonexistent_status_returns_422(self) -> None:
        payload = self._create_reservation()
        response = self.client.put(
            f"/api/reservations/{payload['id']}",
            data={"status_id": 999999},
            content_type="application/json",
            **self._library_admin_headers(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Status not found")

    def test_cancel_nonexistent_reservation_returns_404(self) -> None:
        response = self.client.delete("/api/reservations/999999", **self._auth_headers())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Reservation not found")


class LibraryReadersApiTests(TestCase):
    def setUp(self) -> None:
        self.library = Library.objects.create(name="Main Library", city="Warszawa")
        self.other_library = Library.objects.create(name="Branch Library", city="Krakow")

        self.book = Book.objects.create(title="Test Book", isbn="9780306406157")
        LibraryBook.objects.create(book=self.book, library=self.library, is_available=True)
        LibraryBook.objects.create(book=self.book, library=self.other_library, is_available=True)

        self.role = Role.objects.create(name="readers-test-admin-role")

        self.admin_user = LibraryUser.objects.create_user(
            username="readers_admin",
            email="readers_admin@example.com",
            password="secret123",
        )
        self.admin_session = SessionToken.objects.create(
            key="readers-admin-token", user=self.admin_user
        )
        LibraryAdmin.objects.create(
            library=self.library, user=self.admin_user, role=self.role
        )

        self.other_admin_user = LibraryUser.objects.create_user(
            username="other_readers_admin",
            email="other_readers_admin@example.com",
            password="secret123",
        )
        self.other_admin_session = SessionToken.objects.create(
            key="other-readers-admin-token", user=self.other_admin_user
        )
        LibraryAdmin.objects.create(
            library=self.other_library, user=self.other_admin_user, role=self.role
        )

        self.reader1 = LibraryUser.objects.create_user(
            username="reader_one",
            email="reader_one@example.com",
            password="secret123",
        )
        self.reader1_session = SessionToken.objects.create(
            key="reader-one-token", user=self.reader1
        )
        self.reader2 = LibraryUser.objects.create_user(
            username="reader_two",
            email="reader_two@example.com",
            password="secret123",
        )
        self.reader2_session = SessionToken.objects.create(
            key="reader-two-token", user=self.reader2
        )
        self.non_reader = LibraryUser.objects.create_user(
            username="non_reader",
            email="non_reader@example.com",
            password="secret123",
        )
        self.non_reader_session = SessionToken.objects.create(
            key="non-reader-token", user=self.non_reader
        )

        self.superuser = LibraryUser.objects.create_superuser(
            username="superuser_readers",
            email="superuser_readers@example.com",
            password="secret123",
        )
        self.superuser_session = SessionToken.objects.create(
            key="superuser-readers-token", user=self.superuser
        )

        pending_status, _ = Status.objects.get_or_create(name="pending")
        Reservation.objects.create(
            reader=self.reader1, library=self.library, book=self.book, status=pending_status
        )
        Reservation.objects.create(
            reader=self.reader2, library=self.library, book=self.book, status=pending_status
        )
        # reader2 also has a reservation at other_library — must NOT appear in self.library results
        Reservation.objects.create(
            reader=self.reader2,
            library=self.other_library,
            book=self.book,
            status=pending_status,
        )

    def _auth(self, session: SessionToken) -> dict:
        return {"HTTP_AUTHORIZATION": f"Bearer {session.key}"}

    def test_readers_endpoint_returns_readers_of_the_library(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers", **self._auth(self.admin_session)
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        reader_ids = {item["id"] for item in payload["items"]}
        self.assertIn(self.reader1.id, reader_ids)
        self.assertIn(self.reader2.id, reader_ids)
        self.assertNotIn(self.non_reader.id, reader_ids)

    def test_readers_endpoint_excludes_users_from_other_library(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.other_library.id}/readers",
            **self._auth(self.other_admin_session),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        reader_ids = {item["id"] for item in payload["items"]}
        self.assertIn(self.reader2.id, reader_ids)
        self.assertNotIn(self.reader1.id, reader_ids)

    def test_readers_endpoint_returns_each_reader_once(self) -> None:
        # reader2 already has 1 reservation at self.library; add a second
        pending_status = Status.objects.get(name="pending")
        Reservation.objects.create(
            reader=self.reader2, library=self.library, book=self.book, status=pending_status
        )
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers", **self._auth(self.admin_session)
        )
        payload = response.json()
        reader_ids = [item["id"] for item in payload["items"]]
        self.assertEqual(len(reader_ids), len(set(reader_ids)))

    def test_readers_endpoint_pagination_structure(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers", **self._auth(self.admin_session)
        )
        payload = response.json()
        for key in ("items", "page", "page_size", "total", "total_pages"):
            self.assertIn(key, payload)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["page"], 1)

    def test_readers_endpoint_pagination_limits_items(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers",
            {"page": 1, "page_size": 1},
            **self._auth(self.admin_session),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["total_pages"], 2)

    def test_readers_endpoint_forbidden_for_regular_user(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers",
            **self._auth(self.non_reader_session),
        )
        self.assertEqual(response.status_code, 403)

    def test_readers_endpoint_forbidden_for_admin_of_different_library(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers",
            **self._auth(self.other_admin_session),
        )
        self.assertEqual(response.status_code, 403)

    def test_readers_endpoint_accessible_by_superuser(self) -> None:
        response = self.client.get(
            f"/api/libraries/{self.library.id}/readers",
            **self._auth(self.superuser_session),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 2)


class BookLibraryFilterApiTests(TestCase):
    def setUp(self) -> None:
        self.user = LibraryUser.objects.create_user(
            username="book_filter_user",
            email="book_filter@example.com",
            password="secret123",
        )
        self.session = SessionToken.objects.create(key="book-filter-token", user=self.user)

        self.library_a = Library.objects.create(name="Library A", city="Warszawa")
        self.library_b = Library.objects.create(name="Library B", city="Krakow")

        self.book_in_a = Book.objects.create(title="Book Only In A", isbn="9780306406157")
        self.book_in_b = Book.objects.create(title="Book Only In B", isbn="9783161484100")
        self.book_in_both = Book.objects.create(title="Book In Both", isbn="9780140449136")

        LibraryBook.objects.create(book=self.book_in_a, library=self.library_a, is_available=True)
        LibraryBook.objects.create(book=self.book_in_b, library=self.library_b, is_available=True)
        LibraryBook.objects.create(book=self.book_in_both, library=self.library_a, is_available=True)
        LibraryBook.objects.create(book=self.book_in_both, library=self.library_b, is_available=True)

    def _auth(self) -> dict:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.session.key}"}

    def test_books_filtered_by_library_id_returns_only_that_library_books(self) -> None:
        response = self.client.get(
            "/api/books", {"library_id": self.library_a.id}, **self._auth()
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(self.book_in_a.id, returned_ids)
        self.assertIn(self.book_in_both.id, returned_ids)
        self.assertNotIn(self.book_in_b.id, returned_ids)

    def test_books_without_library_filter_returns_all_books(self) -> None:
        response = self.client.get("/api/books", **self._auth())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(self.book_in_a.id, returned_ids)
        self.assertIn(self.book_in_b.id, returned_ids)
        self.assertIn(self.book_in_both.id, returned_ids)

    def test_books_filter_by_library_b_returns_only_b_books(self) -> None:
        response = self.client.get(
            "/api/books", {"library_id": self.library_b.id}, **self._auth()
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item["id"] for item in payload["items"]}
        self.assertIn(self.book_in_b.id, returned_ids)
        self.assertIn(self.book_in_both.id, returned_ids)
        self.assertNotIn(self.book_in_a.id, returned_ids)