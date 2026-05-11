"""
Exemplos de tarefas em background auditadas como eventos de sistema.
"""

from drf_audit_trail.audit_log import record_system_event
from core.models import Product


def recalculate_product_prices():
    products = Product.objects.all()
    updated = []

    for product in products:
        old_price = product.price
        product.price = (product.price * 110 / 100).quantize(old_price)
        product.save(update_fields=["price"])
        updated.append(
            {
                "old": str(old_price),
                "new": str(product.price),
            }
        )

        record_system_event(
            event_type="System",
            action_description=f"Recalculated price for product {product.id}",
            field_name="Price",
            new_values=str(product.price),
            old_values=str(old_price),
            reason_for_change="Manual 10% inflation adjustment",
        )

    print(f"[recalculate_product_prices] {len(updated)} product(s) updated.")
    return updated


def archive_inactive_products():
    zero_stock = list(Product.objects.filter(quantity=0).values("id", "name", "code"))
    unnamed = list(Product.objects.filter(name="").values("id", "code"))

    record_system_event(
        event_type="System",
        action_description="Archived products with zero quantity",
        extra_informations={"trigger": "manual_shell"},
    )

    print(
        f"[archive_inactive_products] zero_stock={len(zero_stock)}, unnamed={len(unnamed)}"
    )
    return {"zero_stock": zero_stock, "unnamed": unnamed}
