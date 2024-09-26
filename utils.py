import matplotlib.pyplot as plt

# labels = ["No audit", "With audit"]
# times = [0.009233236312866211, 0.024466991424560547]

# plt.figure(figsize=(8, 5))
# plt.bar(labels, times, color=["green", "blue"])
# plt.title("Performance Impact: Process Audit")
# plt.ylabel("Response Time (ms)")
# plt.show()

import io
import base64
from django.shortcuts import render
from django.db.models import Q
from drf_audit_trail.models import RequestAuditEvent


def performance_graph_view(request):
    audit_data = RequestAuditEvent.objects.exclude(
        Q(url__startswith="/test") | Q(url__startswith="/favicon")
    )

    endpoints = []
    avg_response_times = []
    request_counts = []
    endpoint_data = {}

    for audit in audit_data:
        if audit.url not in endpoint_data:
            endpoint_data[audit.url] = {
                "total_time": audit.response_time,
                "count": 1,
            }
        else:
            endpoint_data[audit.url]["total_time"] += audit.response_time
            endpoint_data[audit.url]["count"] += 1

    for endpoint, data in endpoint_data.items():
        avg_response_time = data["total_time"] / data["count"]
        endpoints.append(endpoint)
        avg_response_times.append(avg_response_time)
        request_counts.append(data["count"])

    # Criar o gráfico ajustando o tamanho para evitar cortes
    fig, ax = plt.subplots(figsize=(10, 6))  # Aumenta o tamanho da figura
    bars = ax.barh(endpoints, avg_response_times, color="skyblue")
    ax.set_xlabel("Average response time (ms)")
    ax.set_title("Performance per Endpoint")

    # Adicionar a quantidade de dados usados para calcular a média em cada barra
    for bar, endpoint in zip(bars, endpoints):
        count = endpoint_data[endpoint][
            "count"
        ]  # Número de requisições para cada endpoint
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"  {count}",
            va="center",
            ha="left",
            fontsize=10,
            color="black",
        )

    # Ajustar para que os textos no eixo Y não sejam cortados
    plt.tight_layout()

    # Converter o gráfico para formato PNG
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    string = base64.b64encode(buf.read())
    uri = "data:image/png;base64," + string.decode("utf-8")
    buf.close()

    return render(request, "performance_graph.html", {"graph": uri})
