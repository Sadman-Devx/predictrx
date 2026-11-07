from django.core.management.base import BaseCommand

from apps.vitals.models import Device


class Command(BaseCommand):
    help = "Create an IoT device and print its token (shown once)."

    def add_arguments(self, parser):
        parser.add_argument("device_id")

    def handle(self, *args, **opts):
        device, token = Device.create_with_token(opts["device_id"])
        self.stdout.write(self.style.SUCCESS(f"Device: {device.device_id}"))
        self.stdout.write(f"Token : {token}")
