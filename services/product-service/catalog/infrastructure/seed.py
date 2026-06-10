from decimal import Decimal

from .models import Book, Category, Electronics, Fashion, Product


def _brand_from_name(name: str) -> str:
    n = (name or "").lower()
    for brand in (
        "Apple",
        "Samsung",
        "Xiaomi",
        "ASUS",
        "Dell",
        "HP",
        "Lenovo",
        "Acer",
        "LG",
        "Sony",
        "JBL",
        "Logitech",
        "Anker",
        "Garmin",
        "Bose",
        "Google",
        "OnePlus",
        "OPPO",
        "realme",
    ):
        if brand.lower() in n:
            return brand
    return ""


def seed() -> None:
    categories = [
        ("Smartphone", "smartphone", "electronics"),
        ("Laptop", "laptop", "electronics"),
        ("Tablet", "tablet", "electronics"),
        ("Smartwatch", "smartwatch", "electronics"),
        ("Audio", "audio", "electronics"),
        ("Accessories", "accessories", "electronics"),
        ("Fiction", "fiction", "book"),
        ("Non-fiction", "non-fiction", "book"),
        ("Children", "children", "book"),
        ("Clothing", "clothing", "fashion"),
        ("Shoes", "shoes", "fashion"),
        ("Bags", "bags", "fashion"),
    ]

    cat_by_slug: dict[str, Category] = {}
    for name, slug, tag in categories:
        c, _ = Category.objects.get_or_create(slug=slug, defaults={"name": name, "tag": tag})
        updates = {}
        if c.name != name:
            updates["name"] = name
        if (c.tag or "") != tag:
            updates["tag"] = tag
        if updates:
            for k, v in updates.items():
                setattr(c, k, v)
            c.save(update_fields=list(updates.keys()))
        cat_by_slug[slug] = c

    electronics_products = [
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
        ("SS-A55-256", "Samsung Galaxy A55 5G 256GB", "Mid-range Samsung phone with strong battery.", "9990000", "VND", "smartphone"),
        ("SS-S23U-256", "Samsung Galaxy S23 Ultra 256GB", "Flagship phone with great zoom camera.", "23990000", "VND", "smartphone"),
        ("PIXEL-8-128", "Google Pixel 8 128GB", "Camera-focused Android phone.", "13990000", "VND", "smartphone"),
        ("ONEPLUS-12-256", "OnePlus 12 256GB", "Fast performance and smooth display.", "17990000", "VND", "smartphone"),
        ("REALME-12P-256", "realme 12 Pro+ 256GB", "Affordable phone with periscope-like zoom.", "8990000", "VND", "smartphone"),
        ("LENOVO-LOQ-15", "Lenovo LOQ 15", "Gaming laptop with RTX graphics.", "22990000", "VND", "laptop"),
        ("DELL-G15-5530", "Dell G15 5530", "Gaming laptop with strong cooling.", "24990000", "VND", "laptop"),
        ("ACER-NITRO-V", "Acer Nitro V", "Budget gaming laptop.", "19990000", "VND", "laptop"),
        ("ASUS-ZEPHYRUS-G14", "ASUS ROG Zephyrus G14", "Compact high-end gaming laptop.", "35990000", "VND", "laptop"),
        ("LG-GRAM-14", "LG Gram 14", "Ultra-light laptop for office.", "26990000", "VND", "laptop"),
        ("IPAD-AIR-M2", "iPad Air M2", "Light tablet for study and creativity.", "16990000", "VND", "tablet"),
        ("GAL-TAB-S9FE", "Galaxy Tab S9 FE", "Android tablet with stylus support.", "10990000", "VND", "tablet"),
        ("XIAOMI-PAD-6", "Xiaomi Pad 6", "Tablet with high refresh display.", "7990000", "VND", "tablet"),
        ("WATCH-ULTRA2", "Apple Watch Ultra 2", "Rugged smartwatch for sports.", "19990000", "VND", "smartwatch"),
        ("GARMIN-FR265", "Garmin Forerunner 265", "Running smartwatch with GPS.", "10990000", "VND", "smartwatch"),
        ("SPEAKER-SOUNDLINK", "Bose SoundLink Flex", "Portable speaker with deep bass.", "3490000", "VND", "audio"),
        ("SENN-MOMENTUM-4", "Sennheiser Momentum 4", "Wireless headphones with long battery.", "8990000", "VND", "audio"),
        ("ANKER-20K", "Anker PowerCore 20000mAh", "Power bank for travel.", "899000", "VND", "accessories"),
        ("HUB-USB-C-7IN1", "USB-C Hub 7-in-1", "HDMI + USB + SD adapter.", "499000", "VND", "accessories"),
        ("MOUSE-LOGI-MX3S", "Logitech MX Master 3S", "Ergonomic wireless mouse.", "2490000", "VND", "accessories"),
        ("KB-LOGI-K380", "Logitech K380", "Compact multi-device keyboard.", "790000", "VND", "accessories"),
        ("IP-15-PLUS", "Iphone 15 Plus", "Sản phẩm iPhone đời mới", "1999000", "VND", "smartphone"),
    ]

    book_products = [
        (
            "BOOK-DUNE",
            "Dune",
            "Epic science fiction novel set on desert planet Arrakis.",
            "320000",
            "VND",
            "fiction",
            {"author": "Frank Herbert", "publisher": "Ace Books", "isbn": "9780441172719", "language": "English"},
        ),
        (
            "BOOK-1984",
            "1984",
            "Dystopian classic about totalitarian surveillance.",
            "280000",
            "VND",
            "fiction",
            {"author": "George Orwell", "publisher": "Secker & Warburg", "isbn": "9780451524935", "language": "English"},
        ),
        (
            "BOOK-SAPIENS",
            "Sapiens: A Brief History of Humankind",
            "Non-fiction exploring human history and evolution.",
            "450000",
            "VND",
            "non-fiction",
            {"author": "Yuval Noah Harari", "publisher": "Harper", "isbn": "9780062316097", "language": "English"},
        ),
        (
            "BOOK-ATOMIC",
            "Atomic Habits",
            "Practical guide to building good habits.",
            "390000",
            "VND",
            "non-fiction",
            {"author": "James Clear", "publisher": "Avery", "isbn": "9780735211292", "language": "English"},
        ),
        (
            "BOOK-HARRY1",
            "Harry Potter and the Philosopher's Stone",
            "First book in the beloved fantasy series.",
            "350000",
            "VND",
            "children",
            {"author": "J.K. Rowling", "publisher": "Bloomsbury", "isbn": "9780747532699", "language": "English"},
        ),
        (
            "BOOK-DE-MAY",
            "Đắc Nhân Tâm",
            "Sách kinh điển về nghệ thuật ứng xử và thu phục lòng người.",
            "89000",
            "VND",
            "non-fiction",
            {"author": "Dale Carnegie", "publisher": "First News", "isbn": "9786041234567", "language": "Vietnamese"},
        ),
    ]

    fashion_products = [
        (
            "FASH-TSHIRT-M",
            "Uniqlo Cotton T-Shirt",
            "Basic crew-neck cotton tee for everyday wear.",
            "199000",
            "VND",
            "clothing",
            {"brand": "Uniqlo", "size": "M", "color": "White", "gender": "Unisex"},
        ),
        (
            "FASH-JEANS-32",
            "Levi's 501 Original Jeans",
            "Classic straight-fit denim jeans.",
            "1299000",
            "VND",
            "clothing",
            {"brand": "Levi's", "size": "32", "color": "Indigo", "gender": "Men"},
        ),
        (
            "FASH-DRESS-S",
            "Zara Floral Midi Dress",
            "Light floral dress for summer occasions.",
            "899000",
            "VND",
            "clothing",
            {"brand": "Zara", "size": "S", "color": "Floral", "gender": "Women"},
        ),
        (
            "FASH-SNEAKER-42",
            "Nike Air Force 1",
            "Iconic white sneakers with classic silhouette.",
            "2799000",
            "VND",
            "shoes",
            {"brand": "Nike", "size": "42", "color": "White", "gender": "Unisex"},
        ),
        (
            "FASH-LOAFER-41",
            "Clarks Leather Loafers",
            "Comfortable leather loafers for office wear.",
            "1899000",
            "VND",
            "shoes",
            {"brand": "Clarks", "size": "41", "color": "Brown", "gender": "Men"},
        ),
        (
            "FASH-BAG-TOTE",
            "Coach Tote Bag",
            "Spacious leather tote for daily use.",
            "4599000",
            "VND",
            "bags",
            {"brand": "Coach", "size": "One Size", "color": "Tan", "gender": "Women"},
        ),
    ]

    def upsert_product(
        sku,
        name,
        description,
        price,
        currency,
        cat_slug,
        main_category,
        *,
        subtype_defaults=None,
    ):
        category = cat_by_slug.get(cat_slug)
        p, created = Product.objects.get_or_create(
            sku=sku,
            defaults={
                "name": name,
                "description": description,
                "price": Decimal(price),
                "currency": currency,
                "category": category,
                "main_category": main_category,
                "is_active": True,
                "ratings": 0,
                "no_of_ratings": 0,
            },
        )
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
        if p.main_category != main_category:
            updates["main_category"] = main_category
        if updates:
            for k, v in updates.items():
                setattr(p, k, v)
            p.save(update_fields=list(updates.keys()))

        subtype_defaults = subtype_defaults or {}
        if main_category == Product.MAIN_CATEGORY_ELECTRONICS:
            brand = subtype_defaults.get("brand") or _brand_from_name(name)
            Electronics.objects.update_or_create(
                product=p,
                defaults={
                    "brand": brand,
                    "color": subtype_defaults.get("color", ""),
                    "warranty_months": subtype_defaults.get("warranty_months", 12),
                },
            )
        elif main_category == Product.MAIN_CATEGORY_BOOK:
            Book.objects.update_or_create(product=p, defaults=subtype_defaults)
        elif main_category == Product.MAIN_CATEGORY_FASHION:
            Fashion.objects.update_or_create(product=p, defaults=subtype_defaults)
        return p

    for sku, name, description, price, currency, cat_slug in electronics_products:
        upsert_product(
            sku,
            name,
            description,
            price,
            currency,
            cat_slug,
            Product.MAIN_CATEGORY_ELECTRONICS,
        )

    for sku, name, description, price, currency, cat_slug, book_fields in book_products:
        upsert_product(
            sku,
            name,
            description,
            price,
            currency,
            cat_slug,
            Product.MAIN_CATEGORY_BOOK,
            subtype_defaults=book_fields,
        )

    for sku, name, description, price, currency, cat_slug, fashion_fields in fashion_products:
        upsert_product(
            sku,
            name,
            description,
            price,
            currency,
            cat_slug,
            Product.MAIN_CATEGORY_FASHION,
            subtype_defaults=fashion_fields,
        )

    # Backfill electronics profile for any legacy product missing subtype row.
    for p in Product.objects.filter(main_category=Product.MAIN_CATEGORY_ELECTRONICS):
        try:
            p.electronics
        except Electronics.DoesNotExist:
            Electronics.objects.create(product=p, brand=_brand_from_name(p.name), warranty_months=12)
