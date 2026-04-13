from decimal import Decimal

from .models import Category, Product


def seed() -> None:
    categories = [
        ("Smartphone", "smartphone"),
        ("Laptop", "laptop"),
        ("Tablet", "tablet"),
        ("Smartwatch", "smartwatch"),
        ("Audio", "audio"),
        ("Accessories", "accessories"),
    ]

    cat_by_slug: dict[str, Category] = {}
    for name, slug in categories:
        c, _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})
        if c.name != name:
            c.name = name
            c.save(update_fields=["name"])
        cat_by_slug[slug] = c

    products = [
        ("IP14-128-BLK", "iPhone 14 128GB Black", "Apple smartphone with 128GB storage.", "16990000", "VND", "smartphone"),
        ("XM-RN13-256", "Xiaomi Redmi Note 13 256GB", "Affordable Android smartphone.", "5990000", "VND", "smartphone"),
        ("LAP-GAME-15", "Gaming Laptop 15-inch", "Laptop for gaming and high performance workloads.", "21990000", "VND", "laptop"),
        ("SS-A36-256", "Samsung Galaxy A36 5G 8GB/256GB", "Smartphone with AI photo features.", "8330000", "VND", "smartphone"),
        ("SS-S24-256", "Samsung Galaxy S24 5G 256GB", "Flagship Android phone.", "22990000", "VND", "smartphone"),
        ("IP15PM-1T", "iPhone 15 Pro Max 1TB", "Apple flagship smartphone.", "37790000", "VND", "smartphone"),
        ("IP14-128", "iPhone 14 128GB", "Apple smartphone.", "16990000", "VND", "smartphone"),
        ("XM-RN14P-256", "Xiaomi Redmi Note 14 Pro 256GB", "Value phone with great camera.", "5850000", "VND", "smartphone"),
        ("OP-A79-256", "OPPO A79 5G 256GB", "Affordable 5G phone.", "6990000", "VND", "smartphone"),
        ("IPAD-10-64", "iPad Gen 10 64GB", "Tablet for study and entertainment.", "9990000", "VND", "tablet"),
        ("GAL-TAB-A9", "Galaxy Tab A9", "Compact Android tablet.", "3990000", "VND", "tablet"),
        ("MBP-14-M3", "MacBook Pro 14-inch M3", "Pro laptop for creators.", "39990000", "VND", "laptop"),
        ("MBA-13-M2", "MacBook Air 13-inch M2", "Lightweight everyday laptop.", "24990000", "VND", "laptop"),
        ("HP-15-I5", "HP 15 i5 12th Gen", "Office laptop with Intel i5.", "14990000", "VND", "laptop"),
        ("ASUS-TUF-15", "ASUS TUF Gaming 15", "Gaming laptop for performance.", "21990000", "VND", "laptop"),
        ("WATCH-7-44", "Galaxy Watch7 44mm", "Smartwatch with health tracking.", "3990000", "VND", "smartwatch"),
        ("WATCH-SE2", "Apple Watch SE 2", "Smartwatch for daily use.", "5990000", "VND", "smartwatch"),
        ("JBL-FLIP7", "JBL Flip 7", "Portable Bluetooth speaker.", "3000000", "VND", "audio"),
        ("SONY-WH1000XM5", "Sony WH-1000XM5", "Noise cancelling headphones.", "7990000", "VND", "audio"),
        ("AIRPODS-PRO2", "AirPods Pro 2", "Wireless earbuds with ANC.", "5990000", "VND", "audio"),
        ("CABLE-USB-C", "USB-C Fast Charging Cable", "Durable 1m cable.", "99000", "VND", "accessories"),
        ("CASE-IP15", "iPhone 15 Case", "Protective case.", "199000", "VND", "accessories"),
        ("CHARGER-33W", "33W Fast Charger", "Fast wall charger.", "249000", "VND", "accessories"),
    ]

    for sku, name, description, price, currency, cat_slug in products:
        category = cat_by_slug.get(cat_slug)
        p, created = Product.objects.get_or_create(
            sku=sku,
            defaults={
                "name": name,
                "description": description,
                "price": Decimal(price),
                "currency": currency,
                "category": category,
                "is_active": True,
            },
        )
        if created:
            continue
        updates = {}
        if p.name != name:
            updates["name"] = name
        if (p.description or "") != (description or ""):
            updates["description"] = description
        if str(p.price) != str(Decimal(price)):
            updates["price"] = Decimal(price)
        if p.currency != currency:
            updates["currency"] = currency
        if p.category_id != (category.id if category else None):
            updates["category"] = category
        if updates:
            for k, v in updates.items():
                setattr(p, k, v)
            p.save(update_fields=list(updates.keys()))

