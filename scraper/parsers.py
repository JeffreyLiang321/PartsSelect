"""
HTML parsers for PartSelect pages.
"""

import re
from bs4 import BeautifulSoup
from typing import Optional

BASE_URL = "https://www.partselect.com"


# Listing page parsers 

def parse_listing_page(html: str) -> list[tuple[str, str]]:
    """Returns (listing_name, absolute_url) pairs from div.nf__part.mb-3 cards."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    for card in soup.select("div.nf__part.mb-3"):
        title_tag = card.select_one("a.nf__part__detail__title")
        if not title_tag:
            continue

        href = title_tag.get("href", "").split("?")[0]
        if not href:
            continue
        if href.startswith("/"):
            href = BASE_URL + href

        if href in seen:
            continue
        seen.add(href)

        name_tag = title_tag.select_one("span")
        name = name_tag.get_text(strip=True) if name_tag else title_tag.get_text(strip=True)
        results.append((name, href))

    return results


def parse_related_links(html: str) -> list[str]:
    """Extract subcategory URLs from the 'Related ... Parts' section at the bottom of a brand page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    for h2 in soup.select("h2.section-title"):
        text = h2.get_text(strip=True)
        if "Related" not in text:
            continue

        nf_links = h2.find_next("ul", class_="nf__links")
        if not nf_links:
            continue

        for a in nf_links.select("a[href]"):
            href = a["href"].split("?")[0]
            if href.startswith("/"):
                href = BASE_URL + href
            if href not in seen and "partselect.com" in href:
                seen.add(href)
                links.append(href)

    return links


def parse_brand_links(html: str) -> list[str]:
    """Extract brand page URLs from the first ul.nf__links on the main appliance page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    nf_links = soup.select_one("ul.nf__links")
    if not nf_links:
        return links

    for a in nf_links.select("a[href]"):
        href = a["href"].split("?")[0]
        if href.startswith("/"):
            href = BASE_URL + href
        if href not in seen and "partselect.com" in href:
            seen.add(href)
            links.append(href)

    return links


# Product detail page parser

def _text(el) -> str:
    return el.get_text(separator=" ", strip=True) if el else ""


def parse_product_page(
    html: str,
    product_url: str,
    appliance_type: str,
    listing_name: str = "",
) -> Optional[dict]:
    """
    Parse a PartSelect product detail page into a flat dict for CSV output.
    listing_name comes from the category page and drives the part_name field.
    Returns None on parse failure.
    """
    soup = BeautifulSoup(html, "html.parser")

    # PS number 
    ps_el = soup.select_one("span[itemprop='productID']")
    ps_number = _text(ps_el) if ps_el else None

    if not ps_number:
        m = re.match(r".*/PS(\d+)-", product_url)
        ps_number = f"PS{m.group(1)}" if m else None

    if not ps_number:
        return None

    #  Manufacturer part number
    mpn_el = soup.select_one("span[itemprop='mpn']")
    mfr_part_number = _text(mpn_el)

    # Brand (from structured markup) 
    brand_el = soup.select_one("span[itemprop='brand'] span[itemprop='name']")
    brand = _text(brand_el)

    #  Part name — "{brand} {appliance} {description}" format 
    if listing_name:
        part_name = listing_name
    else:
        h1 = soup.select_one("h1")
        raw_name = _text(h1) if h1 else ""
        prefix = f"{brand} {appliance_type.capitalize()}"
        if brand and not raw_name.startswith(brand):
            part_name = f"{prefix} {raw_name}".strip()
        else:
            part_name = raw_name

    # Price 
    price_el = (
        soup.select_one("span.price.pd__price span.js-partPrice")
        or soup.select_one("span.js-partPrice")
    )
    price_text = _text(price_el).replace("$", "").replace(",", "").strip()
    try:
        price = float(price_text)
    except ValueError:
        price = None

    # Availability
    avail_el = soup.select_one("span[itemprop='availability']")
    availability = _text(avail_el) if avail_el else ""
    in_stock = 1 if "stock" in availability.lower() else 0

    # Install video URL
    # Scoped to pd__img__thumbs — there's also a generic OEM promo yt-video elsewhere on the page.
    install_video_url = ""
    thumbs_container = soup.select_one("div.pd__img__thumbs.js-imgViewerThumbs")
    if thumbs_container:
        repair_vid = thumbs_container.select_one(
            'a[data-part-media-type="RepairVideo"][data-source-id]'
        )
        if repair_vid:
            vid_id = repair_vid.get("data-source-id", "").strip()
            if vid_id:
                install_video_url = f"https://www.youtube.com/watch?v={vid_id}"

    # Replace parts 
    replace_el = soup.select_one(
        'div[data-collapse-container=\'{"targetClassToggle":"d-none"}\']'
    )
    replace_parts = ""
    if replace_el:
        replace_parts = _text(replace_el).replace("This part replaces:", "").strip()

    # Symptoms + appliance_types 
    symptoms = ""
    appliance_types = ""

    pd_wrap = soup.select_one("div.pd__wrap.row")
    if pd_wrap:
        for info_div in pd_wrap.select("div.col-md-6.mt-3"):
            header_el = info_div.select_one("div.bold.mb-1")
            if not header_el:
                continue
            header_text = _text(header_el)

            if "fixes the following symptoms" in header_text.lower():
                items = [_text(li) for li in info_div.select("li") if _text(li)]
                symptoms = " | ".join(items)
            elif "works with the following products" in header_text.lower():
                items = [_text(li) for li in info_div.select("li") if _text(li)]
                appliance_types = " | ".join(items) if items else _text(info_div).replace(header_text, "").strip()

    # Install difficulty + time 
    # First p.bold = difficulty, second = time (both in pd__repair-rating__container).
    install_difficulty = ""
    install_time = ""

    repair_container = soup.select_one("div.pd__repair-rating__container")
    if repair_container:
        bold_ps = repair_container.select("p.bold")
        if len(bold_ps) >= 1:
            install_difficulty = _text(bold_ps[0]).replace(" ", "").strip()
        if len(bold_ps) >= 2:
            install_time = _text(bold_ps[1]).replace(" ", "").strip()

    # Description
    description = ""
    desc_el = soup.select_one("div.pd__description")
    if desc_el:
        description = _text(desc_el)[:1500]
    elif pd_wrap:
        best = ""
        for p in pd_wrap.select("p"):
            t = _text(p)
            if len(t) > len(best) and len(t) > 80:
                best = t
        description = best[:1500]

    # Compatible models
    # The "Model Cross Reference" section uses div.pd__crossref as container.
    # Each model number is an <a href="/Models/{model}/"> inside div.pd__crossref__list.
    # "Load more" means we only capture the initially rendered rows (~20-30),
    # which is sufficient for compatibility lookups.
    compatible_models = []
    seen_models: set[str] = set()

    crossref = soup.select_one("div.pd__crossref")
    if crossref:
        for a in crossref.select("div.pd__crossref__list a[href]"):
            href = a.get("href", "")
            if "/Models/" in href:
                model = a.get_text(strip=True)
                if model and model not in seen_models:
                    seen_models.add(model)
                    compatible_models.append(model)

    compatible_models_str = " | ".join(compatible_models[:50])

    # Image URL 
    img_el = soup.select_one("img[itemprop='image']") or soup.select_one("div.pd__image img")
    image_url = img_el.get("src", "") if img_el else ""

    # Rating + review count 
    rating = None
    review_count = 0

    rating_el = soup.select_one("div.pd__cust-review__header__rating__chart--border")
    if rating_el:
        try:
            rating = float(_text(rating_el).strip())
        except ValueError:
            pass

    review_el = soup.select_one("span.rating__count.lg")
    if review_el:
        review_text = _text(review_el)
        m_rev = re.search(r"(\d[\d,]*)", review_text)
        if m_rev:
            try:
                review_count = int(m_rev.group(1).replace(",", ""))
            except ValueError:
                pass

    return {
        "part_name":          part_name,
        "part_id":            ps_number,
        "mpn_id":             mfr_part_number,
        "part_price":         price,
        "install_difficulty": install_difficulty,
        "install_time":       install_time,
        "symptoms":           symptoms,
        "appliance_types":    appliance_types,
        "replace_parts":      replace_parts,
        "brand":              brand,
        "availability":       availability,
        "in_stock":           in_stock,
        "install_video_url":  install_video_url,
        "product_url":        product_url,
        "appliance_type":     appliance_type,
        "description":        description,
        "compatible_models":  compatible_models_str,
        "image_url":          image_url,
        "rating":             rating,
        "review_count":       review_count,
    }