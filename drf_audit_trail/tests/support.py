import io
import logging
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import Client, TestCase
from django.urls import reverse

from drf_audit_trail.models import LoginAuditEvent, ProcessAuditEvent, RequestAuditEvent
