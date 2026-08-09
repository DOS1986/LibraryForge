import uuid

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from catalog.services.resolver import (
    resolve_library_semantics,
)

from libraries.models import Library


class Command(BaseCommand):
    help = (
        "Rebuild LibraryForge semantic Movie/TV "
        "matches from already-indexed files and NFOs "
        "without running filesystem discovery or ffprobe."
    )

    def add_arguments(
        self,
        parser,
    ):
        group = (
            parser
            .add_mutually_exclusive_group(
                required=True
            )
        )

        group.add_argument(
            "--library",
            dest="library_id",
            help=(
                "Library UUID to rebuild."
            ),
        )

        group.add_argument(
            "--all",
            action="store_true",
            help=(
                "Rebuild all Movie/TV/Auto/Mixed libraries."
            ),
        )

    def handle(
        self,
        *args,
        **options,
    ):
        if options[
            "library_id"
        ]:
            try:
                library_id = uuid.UUID(
                    options[
                        "library_id"
                    ]
                )

            except ValueError as exc:
                raise CommandError(
                    "Invalid library UUID."
                ) from exc

            libraries = (
                Library.objects
                .filter(
                    id=library_id
                )
            )

            if not libraries.exists():
                raise CommandError(
                    "Library not found."
                )

        else:
            libraries = (
                Library.objects
                .filter(
                    content_type__in=[
                        "movies",
                        "tv",
                        "auto",
                        "mixed",
                    ]
                )
                .order_by(
                    "name"
                )
            )

        for library in libraries:
            self.stdout.write(
                (
                    f"Rebuilding semantic catalog: "
                    f"{library.name}"
                )
            )

            result = (
                resolve_library_semantics(
                    library=library
                )
            )

            self.stdout.write(
                self.style.SUCCESS(
                    (
                        f"  matched={result['matched']} "
                        f"unresolved={result['unresolved']} "
                        f"conflict={result['conflict']} "
                        f"locked={result['locked']} "
                        f"errors={result['error_count']}"
                    )
                )
            )

            for error in (
                result[
                    "errors"
                ][:10]
            ):
                self.stdout.write(
                    self.style.WARNING(
                        (
                            "  "
                            f"{error['path']}: "
                            f"{error['error']}"
                        )
                    )
                )

            if (
                result[
                    "error_count"
                ]
                > 10
            ):
                self.stdout.write(
                    self.style.WARNING(
                        (
                            "  Additional errors omitted: "
                            f"{result['error_count'] - 10}"
                        )
                    )
                )
