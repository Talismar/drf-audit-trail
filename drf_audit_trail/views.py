from drf_audit_trail.models import ProcessAuditEvent
from django.http import HttpResponse
from weasyprint import HTML
from django.template.loader import get_template


def process_report_view(request):
    processes = ProcessAuditEvent.objects.prefetch_related("steps__registrations").all()

    template = get_template("report_pdf.html")
    html_content = template.render({"processes": processes})

    pdf_file = HTML(string=html_content).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="process_report.pdf"'
    return response
