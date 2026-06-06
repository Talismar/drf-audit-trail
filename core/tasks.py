"""
Exemplos de tarefas em background auditadas como eventos de sistema.
"""

from core.models import Product
from drf_audit_trail.manager_audit import audit_model_context
from drf_audit_trail.models import AuditLogEntry


def recalculate_product_prices():
    products = Product.objects.all()
    updated = []

    for product in products:
        old_price = product.price
        product.price = (product.price * 110 / 100).quantize(old_price)
        with audit_model_context(
            actor_identifier="system",
            actor_role="System",
            actor_type=AuditLogEntry.SYSTEM,
            reason_for_change="Manual 10% inflation adjustment",
            action_description=f"Recalculated price for product {product.id}",
            model=product,
            fields=["price"],
        ):
            product.save(update_fields=["price"])
        updated.append(
            {
                "old": str(old_price),
                "new": str(product.price),
            }
        )

    print(f"[recalculate_product_prices] {len(updated)} product(s) updated.")
    return updated


def archive_inactive_products():
    zero_stock = list(Product.objects.filter(quantity=0).values("id", "name", "code"))
    unnamed = list(Product.objects.filter(name="").values("id", "code"))

    print(
        f"[archive_inactive_products] zero_stock={len(zero_stock)}, unnamed={len(unnamed)}"
    )
    return {"zero_stock": zero_stock, "unnamed": unnamed}
