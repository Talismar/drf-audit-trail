from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from weasyprint import HTML
from django.template.loader import get_template

from drf_audit_trail.models import ProcessAuditEvent


def render_process_report_response(
    processes,
    filename="process_report.pdf",
    content_disposition="inline",
):
    template = get_template("report_pdf.html")
    html_content = template.render({"processes": processes})

    pdf_file = HTML(string=html_content).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'{content_disposition}; filename="{filename}"'
    )
    return response


def get_process_for_report(process_id):
    return get_object_or_404(
        ProcessAuditEvent.objects.prefetch_related("steps__registrations"),
        pk=process_id,
    )


def process_report_view(request):
    processes = ProcessAuditEvent.objects.prefetch_related("steps__registrations").all()
    return render_process_report_response(processes)
