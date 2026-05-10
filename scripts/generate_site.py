#!/usr/bin/env python3
"""Generate the static site from contents-codex.md.

The content file is Markdown for humans with a single fenced `content` block for
the generator. The parser intentionally supports only the small subset we use:
sections, array sections, strings, multi-line strings, integers, and string
arrays. That keeps the repo dependency-free on Python 3.9.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTENT_FILE = ROOT / "contents.md"
PAGE_ORDER = ["home", "program", "why_cbti", "about", "testimonials", "faqs", "contact"]
PAGE_FILES = {
    "home": "index.html",
    "program": "program.html",
    "why_cbti": "why-cbti.html",
    "about": "about.html",
    "testimonials": "testimonials.html",
    "faqs": "faqs.html",
    "contact": "contact.html",
}

META_DEFAULTS = {
    "home": {
        "title": "Insomnia Warriors — Clinical CBT-I Program for Chronic Insomnia",
        "description": "Insomnia Warriors delivers a clinically grounded CBT-I program to help you reclaim restful sleep. Led by Tierza Clerc, OTR/L, CBT-I — 26 years of clinical experience.",
        "og_title": "Insomnia Warriors — Clinical CBT-I Program for Chronic Insomnia",
        "og_description": "Clinically grounded CBT-I treatment for chronic insomnia. Led by Tierza Clerc, OTR/L — 26 years of clinical experience.",
    },
    "program": {
        "title": "The Program — Insomnia Warriors",
        "description": "A clinically grounded, multi-component CBT-I treatment program for chronic insomnia. Learn about our structured approach to restoring natural sleep.",
    },
    "why_cbti": {
        "title": "Why CBT-I — Insomnia Warriors",
        "description": "CBT-I is the gold standard treatment for chronic insomnia. Learn why it works better than medication — with lasting results and no side effects.",
    },
    "about": {
        "title": "Meet Tierza Clerc — Insomnia Warriors",
        "description": "Meet Tierza Clerc, OTR/L, CBT-I — a therapist with 26 years of clinical experience who has walked the same path to better sleep.",
    },
    "testimonials": {
        "title": "Testimonials — Insomnia Warriors",
        "description": "Real cases, measurable improvement, restored sleep. Read what clients say about their CBT-I treatment experience with Insomnia Warriors.",
        "og_description": "Real cases, measurable improvement, restored sleep. Read what clients say about their CBT-I treatment experience.",
    },
    "faqs": {
        "title": "FAQs — Insomnia Warriors",
        "description": "Common questions about CBT-I treatment, session structure, insurance, sleep diaries, and what to expect from the Insomnia Warriors program.",
        "og_description": "Common questions about CBT-I treatment, session structure, insurance, sleep diaries, and what to expect from the program.",
    },
    "contact": {
        "title": "Contact — Insomnia Warriors",
        "description": "Get started with CBT-I treatment. Contact Insomnia Warriors to schedule a consultation and take the first step toward better sleep.",
    },
}

ICON_DEFAULTS = {
    "home.symptoms": ["&#9790;", "&#9200;", "&#9788;", "&#10067;", "&#9889;", "&#9899;"],
    "home.why_works": ["&#9998;", "&#10084;", "&#9632;", "&#9733;", "&#9829;"],
    "program.components": ["&#9998;", "&#9881;", "&#10084;"],
    "why_cbti.cards": ["&#9650;", "&#9745;", "&#8635;", "&#9881;", "&#10024;"],
    "why_cbti.ot_cards": ["&#9733;", "&#9881;", "&#10084;", "&#9745;", "&#10024;"],
}

SHARED_ABOUT_IMAGES = {
    "image": "images/tierza-clerc.png",
    "image_alt": "Tierza Clerc, OTR/L, CBT-I",
    "logo_1_image": "images/uw-medicine.png",
    "logo_1_alt": "UW Medicine",
    "logo_1_url": "https://www.uwmedicine.org",
    "logo_2_image": "images/colorado-state.png",
    "logo_2_alt": "Colorado State University",
    "logo_2_url": "https://www.colostate.edu",
}


def extract_content_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```content\n(.*?)\n```", text, re.S)
    if not match:
        raise ValueError(f"{path} must contain one fenced ```content block")
    return match.group(1)


def parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith('"""') and raw.endswith('"""'):
        return raw[3:-3]
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1].replace('\\"', '"')
    if raw.startswith("[") and raw.endswith("]"):
        body = raw[1:-1].strip()
        if not body:
            return []
        return [parse_scalar(item) for item in split_array(body)]
    if raw.isdigit():
        return int(raw)
    raise ValueError(f"Unsupported value syntax: {raw}")


def split_array(body: str) -> list[str]:
    items: list[str] = []
    chunk: list[str] = []
    in_string = False
    escape = False
    for char in body:
        if escape:
            chunk.append(char)
            escape = False
            continue
        if char == "\\":
            chunk.append(char)
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            chunk.append(char)
            continue
        if char == "," and not in_string:
            items.append("".join(chunk).strip())
            chunk = []
            continue
        chunk.append(char)
    if chunk:
        items.append("".join(chunk).strip())
    return items


def set_path(root: dict[str, Any], path: list[str], value: Any) -> None:
    cursor = root
    for part in path[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[path[-1]] = value


def get_section(root: dict[str, Any], path: list[str]) -> dict[str, Any]:
    cursor = root
    for part in path:
        cursor = cursor.setdefault(part, {})
        if isinstance(cursor, list):
            raise ValueError(f"Cannot descend into list section: {'.'.join(path)}")
    return cursor


def add_array_section(root: dict[str, Any], path: list[str]) -> dict[str, Any]:
    cursor = root
    for part in path[:-1]:
        cursor = cursor.setdefault(part, {})
    array = cursor.setdefault(path[-1], [])
    if not isinstance(array, list):
        raise ValueError(f"Section {'.'.join(path)} is not an array")
    item: dict[str, Any] = {}
    array.append(item)
    return item


def parse_content(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    lines = iter(enumerate(text.splitlines(), start=1))

    for lineno, line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[[") and stripped.endswith("]]"):
            current = add_array_section(data, stripped[2:-2].split("."))
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = get_section(data, stripped[1:-1].split("."))
            continue
        if current is None:
            raise ValueError(f"Line {lineno}: key/value before section")
        if "=" not in stripped:
            raise ValueError(f"Line {lineno}: expected key = value")
        key, raw = [part.strip() for part in stripped.split("=", 1)]
        if raw == '"""':
            chunks: list[str] = []
            for _, continuation in lines:
                if continuation.strip() == '"""':
                    break
                chunks.append(continuation)
            current[key] = "\n".join(chunks).strip()
        else:
            current[key] = parse_scalar(raw)

    return data


def parse_input_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"```content\n(.*?)\n```", raw, re.S)
    if match:
        return parse_content(match.group(1))
    return parse_friendly_markdown(raw)


def parse_friendly_markdown(raw: str) -> dict[str, Any]:
    """Parse the editor-friendly Markdown format used by contents-codex.md."""

    def section(title: str) -> str:
        pattern = rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)"
        match = re.search(pattern, raw, re.S | re.M)
        if not match:
            raise ValueError(f"Missing section: {title}")
        return match.group(1).strip()

    def page(title: str) -> str:
        return section(f"Page: {title}")

    def subsection(block: str, title: str) -> str:
        pattern = rf"^### {re.escape(title)}\n(.*?)(?=^### |\Z)"
        match = re.search(pattern, block, re.S | re.M)
        if not match:
            raise ValueError(f"Missing subsection: {title}")
        return match.group(1).strip()

    def bullets(block: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            body = line[2:]
            if ":" in body:
                key, value = body.split(":", 1)
                values[key.strip()] = value.strip()
        return values

    def button_value(value: str) -> dict[str, str]:
        label, url = link_value(value)
        return {"text": label, "url": url}

    def link_value(value: str) -> tuple[str, str]:
        match = re.match(r"(.+?)\s+\[Link:\s*([^\]]+)\](?:\s*\(button\))?$", value)
        if not match:
            raise ValueError(f"Expected '[Link: ...]' value: {value}")
        return match.group(1).strip(), match.group(2).strip()

    def plain_link_item(line: str) -> dict[str, str]:
        label, url = link_value(line[2:].strip())
        return {"label": label, "url": url}

    def numbered_items(values: dict[str, str], prefix: str, count: int, icons_key: str | None = None) -> list[dict[str, str]]:
        icons = ICON_DEFAULTS.get(icons_key or "", [])
        items = []
        for index in range(1, count + 1):
            item = {"text": values[f"{prefix} {index}"]}
            if icons:
                item["icon"] = icons[index - 1]
            items.append(item)
        return items

    def cards(values: dict[str, str], count: int, icons_key: str, prefix: str = "Card") -> list[dict[str, Any]]:
        result = []
        for index in range(1, count + 1):
            item: dict[str, Any] = {
                "icon": ICON_DEFAULTS[icons_key][index - 1],
                "title": values[f"{prefix} {index} title"],
                "text": values[f"{prefix} {index} text"],
            }
            result.append(item)
        return result

    def paragraphs_from_values(values: dict[str, str]) -> list[str]:
        result = []
        index = 1
        while f"Paragraph {index}" in values:
            result.append(values[f"Paragraph {index}"])
            index += 1
        return result

    def page_header(block: str) -> dict[str, str]:
        values = bullets(subsection(block, "Page Header"))
        return {"label": values["Section label"], "heading": values["Heading"], "subtitle": values["Subtitle"]}

    def cta_block(block: str) -> dict[str, Any]:
        values = bullets(subsection(block, "Call to Action"))
        return {"heading": values["Heading"], "text": values["Text"], "button": button_value(values["Button"])}

    header_lines = [line for line in section("Header (appears on every page)").splitlines() if line.strip().startswith("- ")]
    nav_key_by_url = {
        "index.html": "home",
        "program.html": "program",
        "why-cbti.html": "why_cbti",
        "about.html": "about",
        "testimonials.html": "testimonials",
        "faqs.html": "faqs",
        "contact.html": "contact",
    }
    nav = []
    for line in header_lines:
        item = plain_link_item(line)
        try:
            item["key"] = nav_key_by_url[item["url"]]
        except KeyError as exc:
            raise ValueError(f"Unknown header link URL: {item['url']}") from exc
        if "(button)" in line:
            item["button"] = "true"
        nav.append(item)

    contact_values = bullets(section("Contact Info (used across all pages)"))
    email_label, email_href = link_value(contact_values["Email"])
    phone_label, phone_href = link_value(contact_values["Phone"])

    data: dict[str, Any] = {
        "site": {
            "name": "Insomnia Warriors",
            "base_url": "https://insomniawarriors.com/",
            "og_image": "https://insomniawarriors.com/images/logo.png",
            "logo_image": "images/logo.png",
            "logo_alt": "Insomnia Warriors",
            "provider_name": "Tierza Clerc",
            "provider_schema_description": "26 years of clinical experience in medical massage and occupational therapy. CBT-I certified.",
            "contact": {
                "email": email_label,
                "phone_display": phone_label,
                "phone_href": phone_href,
                "phone_schema": "+1-253-223-1751",
                "payment": contact_values["Payment"],
            },
            "footer": {
                "tagline": contact_values["Footer tagline"],
                "contact_heading": "Contact",
                "cta_text": "Get Started",
                "cta_url": "contact.html",
                "copyright": contact_values["Copyright"],
                "credential": contact_values["Footer credential"],
                "disclaimer": contact_values["Disclaimer"],
            },
            "nav": nav,
        },
        "pages": {},
    }

    # Home
    block = page("Home")
    hero = bullets(subsection(block, "Hero"))
    meet = bullets(subsection(block, "Meet Tierza (preview)"))
    stats_values = bullets(subsection(block, "Stat Bar"))
    who_values = bullets(subsection(block, "Who This Program Is For"))
    why_values = bullets(subsection(block, "Why This Works"))
    data["pages"]["home"] = {
        "meta": META_DEFAULTS["home"],
        "hero": {
            "headline": hero["Headline"],
            "subtitle": hero["Subtitle"],
            "description": hero["Description"],
            "primary_button": button_value(hero["Button 1"]),
            "secondary_button": button_value(hero["Button 2"]),
        },
        "meet_tierza": {
            **SHARED_ABOUT_IMAGES,
            "credential_tag": meet["Credential tag"],
            "heading": meet["Heading"],
            "subtitle": meet["Subtitle"],
            "bio": meet["Bio"],
            "button": button_value(meet["Button"]),
        },
        "stats": [
            {"number": stats_values["Stat 1"].split(" — ", 1)[0], "label": stats_values["Stat 1"].split(" — ", 1)[1]},
            {"number": stats_values["Stat 2"].split(" — ", 1)[0], "label": stats_values["Stat 2"].split(" — ", 1)[1]},
        ],
        "who_for": {
            "label": who_values["Section label"],
            "heading": who_values["Heading"],
            "description": who_values["Description"],
            "footnote": who_values["Footnote"],
            "symptoms": numbered_items(who_values, "Symptom", 6, "home.symptoms"),
        },
        "why_works": {
            "label": why_values["Section label"],
            "heading": why_values["Heading"],
            "description": why_values["Description"],
            "cards": cards(why_values, 5, "home.why_works"),
        },
        "cta": cta_block(block),
    }

    # Program
    block = page("The Program")
    components = bullets(subsection(block, "Program Components"))
    steps = bullets(subsection(block, "How The Program Works"))
    note = bullets(subsection(block, "Note About Underlying Conditions"))
    data["pages"]["program"] = {
        "meta": META_DEFAULTS["program"],
        "page_header": page_header(block),
        "components": {
            "label": components["Section label"],
            "heading": components["Heading"],
            "description": components["Description"],
            "footnote": components["Footnote"],
            "items": [
                {"icon": ICON_DEFAULTS["program.components"][i - 1], "title": components[f"Component {i} title"], "text": components[f"Component {i} text"]}
                for i in range(1, 4)
            ],
        },
        "steps": {
            "label": steps["Section label"],
            "heading": steps["Heading"],
            "items": [{"title": steps[f"Step {i} title"], "text": steps[f"Step {i} text"]} for i in range(1, 6)],
        },
        "note": {"heading": note["Heading"], "paragraphs": paragraphs_from_values(note)},
        "cta": cta_block(block),
    }

    # Why CBT-I
    block = page("Why OT driven CBT-I")
    root_cause_raw = subsection(block, "CBT-I Treats the Root Cause")
    # The OT sub-section is embedded with a "- ### " prefix (not a real subsection)
    ot_split = re.split(r"^- ### .+$", root_cause_raw, maxsplit=1, flags=re.M)
    root_cause = bullets(ot_split[0])
    why_cards = cards(root_cause, 5, "why_cbti.cards")
    for item in why_cards:
        if ": " in item["text"] and item["text"].endswith(".") is False:
            pass
    for item in why_cards:
        if ": " in item["text"]:
            intro, raw_bullets = item["text"].split(": ", 1)
            item["text"] = intro + ":"
            item["bullets"] = [capitalize_first(part.strip().rstrip(".")) for part in raw_bullets.split(",")]
    comparison = []
    for line in subsection(block, "CBT-I vs. Medication Comparison").splitlines():
        if line.startswith("| ") and "---" not in line and not line.startswith("| Factor"):
            parts = [part.strip() for part in line.strip("|").split("|")]
            comparison.append({"factor": parts[0]})
    why_cbti_data: dict[str, Any] = {
        "meta": META_DEFAULTS["why_cbti"],
        "page_header": page_header(block),
        "root_cause": {
            "label": root_cause["Section label"],
            "heading": root_cause["Heading"],
            "description": root_cause["Description"],
            "cards": why_cards,
        },
        "comparison": {
            "label": "CBT-I vs. Medication",
            "heading": "Why Choose CBT-I Over Sleep Medication?",
            "caption": "Comparison of CBT-I versus sleep medication across key treatment factors",
            "column_1": "CBT-I",
            "column_2": "Sleep Medication",
            "rows": comparison,
        },
        "cta": cta_block(block),
    }
    # Parse the OT-driven CBT-I sub-section if present
    if len(ot_split) > 1:
        ot_values = bullets(ot_split[1])
        # Handle case-inconsistent keys (e.g. "card 3 text" vs "Card 3 text")
        ot_values_ci = {k.lower(): v for k, v in ot_values.items()}
        ot_cards_list = []
        for i in range(1, 6):
            title = ot_values_ci.get(f"card {i} title", "")
            card_text = ot_values_ci.get(f"card {i} text", "")
            ot_cards_list.append({"icon": ICON_DEFAULTS["why_cbti.ot_cards"][i - 1], "title": title, "text": card_text})
        why_cbti_data["ot_diff"] = {
            "label": ot_values_ci.get("section label", ""),
            "heading": ot_values_ci.get("heading", ""),
            "description": ot_values_ci.get("description", ""),
            "cards": ot_cards_list,
        }
    data["pages"]["why_cbti"] = why_cbti_data

    # About
    block = page("Meet The Team")
    bio = bullets(subsection(block, "Bio"))
    philosophy = bullets(subsection(block, "Why The Team Does This Work"))
    data["pages"]["about"] = {
        "meta": META_DEFAULTS["about"],
        "page_header": page_header(block),
        "bio": {**SHARED_ABOUT_IMAGES, "credential_tag": bio["Credential tag"], "heading": bio["Heading"], "paragraphs": paragraphs_from_values(bio)},
        "philosophy": {"label": philosophy["Section label"], "heading": philosophy["Heading"], "paragraphs": paragraphs_from_values(philosophy)},
        "cta": cta_block(block),
    }

    # Testimonials
    block = page("Testimonials")
    testimonial_items = []
    for index in range(1, 4):
        values = bullets(subsection(block, f"Testimonial {index}"))
        quote = values["Quote"].strip()
        if quote.startswith('"') and quote.endswith('"'):
            quote = quote[1:-1]
        testimonial_items.append({
            "author": values["Author"],
            "image": values["Image"],
            "image_alt": values["Author"],
            "rating": int(values["Rating"].split()[0]),
            "quote": quote,
        })
    social_text = bullets(subsection(block, "Social Proof"))["Text"]
    strong, social = social_text.split(" — ", 1)
    data["pages"]["testimonials"] = {
        "meta": META_DEFAULTS["testimonials"],
        "page_header": page_header(block),
        "testimonials": testimonial_items,
        "social_proof": {"strong": strong, "text": social},
        "privacy_note": bullets(subsection(block, "Privacy Note"))["Text"],
        "cta": cta_block(block),
    }

    # FAQs
    block = page("FAQs")
    question_matches = re.findall(r"^### Question(?: \d+)?: (.*?)\n\n(.*?)(?=^### Question(?: \d+)?:|^### Call to Action|\Z)", block, re.S | re.M)
    data["pages"]["faqs"] = {
        "meta": META_DEFAULTS["faqs"],
        "page_header": page_header(block),
        "questions": [{"question": q.strip(), "answer": a.strip()} for q, a in question_matches],
        "cta": cta_block(block),
    }

    # Contact
    block = page("Contact")
    reach = bullets(subsection(block, "Reach Out"))
    form = bullets(subsection(block, "Contact Form"))
    confirmation = bullets(subsection(block, "After Submission"))
    fallback_text, _ = link_value(confirmation["Fallback"])
    data["pages"]["contact"] = {
        "meta": META_DEFAULTS["contact"],
        "page_header": page_header(block),
        "reach_out": {"heading": reach["Heading"], "description": reach["Description"]},
        "expect": {"heading": "What to Expect", "text": subsection(block, "What to Expect").strip()},
        "form": {
            "heading": form["Form heading"],
            "first_name": "First Name",
            "last_name": "Last Name",
            "email": "Email",
            "phone": "Phone",
            "concern": "Primary Concern",
            "concern_placeholder": "Select one...",
            "concern_options": [part.strip() for part in form["Primary Concern options"].split(",")],
            "message_label": "Tell Us About Your Sleep",
            "message_placeholder": form["Message prompt"],
            "submit": form["Submit button"],
        },
        "confirmation": {
            "heading": confirmation["Heading"],
            "text_prefix": "Your email client should now be open with your message ready to send. Please press",
            "strong": "Send",
            "text_suffix": "in your email app to complete your inquiry.",
            "fallback_prefix": fallback_text.replace(" Click here to email us directly.", ""),
            "fallback_link": "Click here to email us directly.",
        },
    }

    return data


def capitalize_first(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def text(value: Any) -> str:
    return html.escape(str(value), quote=False)


def paragraphs(value: str) -> str:
    return "\n".join(f"        <p>{text(part.strip())}</p>" for part in value.split("\n\n") if part.strip())


def button(item: dict[str, Any], class_name: str = "btn btn-outline") -> str:
    return f'<a href="{esc(item["url"])}" class="{class_name}">{text(item["text"])}</a>'


def head(page_key: str, page: dict[str, Any], site: dict[str, Any]) -> str:
    meta = page["meta"]
    url = site["base_url"] if page_key == "home" else f'{site["base_url"]}{PAGE_FILES[page_key]}'
    schema = schema_for(page_key, page, site, url)
    return f"""<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{text(meta["title"])}</title>
  <meta name="description" content="{esc(meta["description"])}">
  <meta property="og:title" content="{esc(meta.get("og_title", meta["title"]))}">
  <meta property="og:description" content="{esc(meta.get("og_description", meta["description"]))}">
  <meta property="og:image" content="{esc(site["og_image"])}">
  <meta property="og:url" content="{esc(url)}">
  <meta property="og:type" content="website">
  <link rel="icon" type="image/png" sizes="32x32" href="images/favicons/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="images/favicons/favicon-16x16.png">
  <link rel="icon" href="images/favicons/favicon.ico" sizes="any">
  <link rel="apple-touch-icon" sizes="180x180" href="images/favicons/apple-touch-icon.png">
  <link rel="manifest" href="site.webmanifest">
  <meta name="theme-color" content="#6CEDEF">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;700&family=Poppins:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="styles.css">
  <script type="application/ld+json">
  {json.dumps(schema, indent=4, ensure_ascii=False)}
  </script>
</head>"""


def schema_for(page_key: str, page: dict[str, Any], site: dict[str, Any], url: str) -> dict[str, Any]:
    contact = site["contact"]
    if page_key == "home":
        return {
            "@context": "https://schema.org",
            "@type": "MedicalBusiness",
            "name": site["name"],
            "description": "Clinically grounded CBT-I (Cognitive Behavioral Therapy for Insomnia) treatment program for chronic insomnia. Led by Tierza Clerc, OTR/L, CBT-I — 26 years of clinical experience.",
            "url": site["base_url"],
            "logo": site["og_image"],
            "image": f'{site["base_url"]}images/tierza-clerc.png',
            "email": contact["email"],
            "telephone": contact["phone_schema"],
            "founder": {
                "@type": "Person",
                "name": site["provider_name"],
                "jobTitle": "Occupational Therapist & CBT-I Provider",
                "description": site["provider_schema_description"],
                "credential": [
                    {"@type": "EducationalOccupationalCredential", "credentialCategory": "OTR/L"},
                    {"@type": "EducationalOccupationalCredential", "credentialCategory": "CBT-I Certified"},
                ],
                "alumniOf": [
                    {"@type": "CollegeOrUniversity", "name": "UW Medicine", "url": "https://www.uwmedicine.org"},
                    {"@type": "CollegeOrUniversity", "name": "Colorado State University", "url": "https://www.colostate.edu"},
                ],
            },
            "medicalSpecialty": "Occupational Therapy",
            "hasOfferCatalog": {
                "@type": "OfferCatalog",
                "name": "CBT-I Treatment Program",
                "itemListElement": [
                    {
                        "@type": "MedicalTherapy",
                        "name": "Cognitive Behavioral Therapy for Insomnia (CBT-I)",
                        "description": "A 7-11 session evidence-based treatment program for chronic insomnia, addressing co-occurring conditions such as anxiety, PTSD, depression, and chronic pain.",
                        "relevantSpecialty": "Occupational Therapy",
                    }
                ],
            },
            "paymentAccepted": "HSA, FSA",
            "sameAs": [],
        }
    if page_key == "program":
        return {
            "@context": "https://schema.org",
            "@type": "MedicalTherapy",
            "name": "CBT-I Treatment Program — Insomnia Warriors",
            "description": "A clinically grounded, multi-component CBT-I treatment program for chronic insomnia. Includes clinical assessment, sleep diaries, personalized treatment plans, weekly sessions, and co-occurring condition integration.",
            "url": url,
            "medicineSystem": "EvidenceBased",
            "relevantSpecialty": "Occupational Therapy",
            "study": {
                "@type": "MedicalStudy",
                "description": "CBT-I has a 95% success rate among individuals who adhere to and complete the program.",
            },
            "provider": {"@type": "MedicalBusiness", "name": site["name"], "url": site["base_url"]},
        }
    if page_key == "why_cbti":
        return {
            "@context": "https://schema.org",
            "@type": "MedicalWebPage",
            "name": page["meta"]["title"],
            "description": page["meta"]["description"],
            "url": url,
            "about": {
                "@type": "MedicalTherapy",
                "name": "Cognitive Behavioral Therapy for Insomnia (CBT-I)",
                "description": "An evidence-based therapy that treats the root cause of insomnia through sleep scheduling, stimulus control, cognitive restructuring, and relaxation techniques. Unlike sleep medication, CBT-I produces long-lasting results with no side effects or dependency risk.",
                "medicineSystem": "EvidenceBased",
            },
        }
    if page_key == "about":
        return {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": site["provider_name"],
            "jobTitle": "Occupational Therapist & CBT-I Provider",
            "description": "Tierza Clerc has been in the medical field for 26 years — initially in medical massage for 23 years and now 3 years in occupational therapy. She is CBT-I certified and dedicated to helping people reclaim restful sleep.",
            "image": f'{site["base_url"]}images/tierza-clerc.png',
            "url": url,
            "worksFor": {"@type": "MedicalBusiness", "name": site["name"], "url": site["base_url"]},
            "credential": [
                {"@type": "EducationalOccupationalCredential", "credentialCategory": "OTR/L"},
                {"@type": "EducationalOccupationalCredential", "credentialCategory": "CBT-I Certified"},
            ],
            "alumniOf": [
                {"@type": "CollegeOrUniversity", "name": "UW Medicine", "url": "https://www.uwmedicine.org"},
                {"@type": "CollegeOrUniversity", "name": "Colorado State University", "url": "https://www.colostate.edu"},
            ],
            "knowsAbout": ["Cognitive Behavioral Therapy for Insomnia", "CBT-I", "Occupational Therapy", "Chronic Insomnia", "Sleep Medicine"],
        }
    if page_key == "testimonials":
        reviews = page["testimonials"]
        return {
            "@context": "https://schema.org",
            "@type": "MedicalBusiness",
            "name": site["name"],
            "url": site["base_url"],
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "5", "reviewCount": str(len(reviews)), "bestRating": "5"},
            "review": [
                {
                    "@type": "Review",
                    "author": {"@type": "Person", "name": review["author"]},
                    "reviewRating": {"@type": "Rating", "ratingValue": str(review["rating"]), "bestRating": "5"},
                    "reviewBody": review["quote"],
                }
                for review in reviews
            ],
        }
    if page_key == "faqs":
        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": item["question"], "acceptedAnswer": {"@type": "Answer", "text": item["answer"].replace("\n\n", " ")}}
                for item in page["questions"]
            ],
        }
    return {
        "@context": "https://schema.org",
        "@type": "ContactPage",
        "name": page["meta"]["title"],
        "description": page["meta"]["description"],
        "url": url,
        "mainEntity": {"@type": "MedicalBusiness", "name": site["name"], "email": contact["email"], "telephone": contact["phone_schema"], "url": site["base_url"]},
    }


def header(active: str, site: dict[str, Any]) -> str:
    links = []
    for item in site["nav"]:
        classes = []
        if item["key"] == active:
            classes.append("active")
        if item.get("button") == "true":
            classes = ["btn", "btn-primary", "nav-cta"] + classes
        class_attr = f' class="{" ".join(classes)}"' if classes else ""
        links.append(f'        <a href="{esc(item["url"])}"{class_attr}>{text(item["label"])}</a>')
    return f"""  <!-- ====== HEADER ====== -->
  <header class="site-header" id="site-header">
    <div class="container header-inner">
      <a href="index.html" class="logo">
        <img src="{esc(site["logo_image"])}" alt="{esc(site["logo_alt"])}" class="logo-img">
      </a>
      <nav class="nav-links" id="nav-links">
{chr(10).join(links)}
      </nav>
      <button class="nav-toggle" id="nav-toggle" aria-label="Toggle navigation">
        <span></span><span></span><span></span>
      </button>
    </div>
  </header>"""


def footer(site: dict[str, Any]) -> str:
    footer_data = site["footer"]
    contact = site["contact"]
    return f"""  <!-- ====== FOOTER ====== -->
  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <a href="index.html" class="logo">
            <img src="{esc(site["logo_image"])}" alt="{esc(site["logo_alt"])}" class="logo-img">
          </a>
          <p>{text(footer_data["tagline"])}</p>
        </div>
        <div class="footer-links">
          <h4>{text(footer_data["contact_heading"])}</h4>
          <a href="mailto:{esc(contact["email"])}">{text(contact["email"])}</a>
          <a href="{esc(contact["phone_href"])}">{text(contact["phone_display"])}</a>
          <a href="{esc(footer_data["cta_url"])}">{text(footer_data["cta_text"])}</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>&copy; {text(footer_data["copyright"])}</span>
        <span>{text(footer_data["credential"])}</span>
      </div>
    </div>
  </footer>
  <div class="disclaimer">{text(footer_data["disclaimer"])}</div>"""


def page_header(section: dict[str, Any]) -> str:
    return f"""  <!-- ====== PAGE HEADER ====== -->
  <section class="page-header">
    <div class="container">
      <span class="section-label">{text(section["label"])}</span>
      <h1>{text(section["heading"])}</h1>
      <p class="subtitle">{text(section["subtitle"])}</p>
    </div>
  </section>"""


def cta(section: dict[str, Any]) -> str:
    return f"""  <!-- ====== CTA ====== -->
  <section class="cta-banner">
    <div class="container">
      <h2>{text(section["heading"])}</h2>
      <p>{text(section["text"])}</p>
      {button(section["button"])}
    </div>
  </section>"""


def about_block(section: dict[str, Any], cream: bool = False) -> str:
    section_class = "section section-cream" if cream else "section"
    paras = "\n".join(f"          <p>{text(p)}</p>" for p in section["paragraphs"])
    return f"""  <section class="{section_class}">
    <div class="container">
      <div class="about-grid">
        <div class="about-image">
          <img src="{esc(section["image"])}" alt="{esc(section["image_alt"])}">
        </div>
        <div class="about-content">
          <div class="credential-block">
            <span class="credential-tag">{text(section["credential_tag"])}</span>
            <div class="credentials-bar">
              <a href="{esc(section["logo_1_url"])}" target="_blank" rel="noopener"><img src="{esc(section["logo_1_image"])}" alt="{esc(section["logo_1_alt"])}"></a>
              <a href="{esc(section["logo_2_url"])}" target="_blank" rel="noopener"><img src="{esc(section["logo_2_image"])}" alt="{esc(section["logo_2_alt"])}"></a>
            </div>
          </div>
          <h2>{text(section["heading"])}</h2>
{paras}
        </div>
      </div>
    </div>
  </section>"""


def render_home(page: dict[str, Any], site: dict[str, Any]) -> str:
    hero = page["hero"]
    about = page["meet_tierza"]
    symptoms = "\n".join(
        f"""        <div class="symptom-card">
          <div class="symptom-icon">{item["icon"]}</div>
          <p>{text(item["text"])}</p>
        </div>"""
        for item in page["who_for"]["symptoms"]
    )
    cards = "\n".join(
        f"""        <div class="diff-card">
          <h4>{text(item["title"])}</h4>
          <p>{text(item["text"])}</p>
        </div>"""
        for item in page["why_works"]["cards"]
    )
    stats = "\n".join(
        f"""      <div class="stat-item">
        <div class="stat-number">{text(item["number"])}</div>
        <div class="stat-label">{text(item["label"])}</div>
      </div>"""
        for item in page["stats"]
    )
    return f"""  <!-- ====== HERO ====== -->
  <section class="hero">
    <div class="container">
      <div class="hero-content">
        <h1>{text(hero["headline"])}</h1>
        <h3 class="hero-subtitle">{text(hero["subtitle"])}</h3>
        <p class="subtitle">{text(hero["description"])}</p>
        <div class="hero-actions">
          {button(hero["primary_button"])}
          {button(hero["secondary_button"])}
        </div>
      </div>
    </div>
  </section>

  <!-- ====== ABOUT TEASER ====== -->
  <section class="section section-cream">
    <div class="container">
      <div class="about-grid">
        <div class="about-image">
          <img src="{esc(about["image"])}" alt="{esc(about["image_alt"])}">
        </div>
        <div class="about-content">
          <div class="credential-block">
            <span class="credential-tag">{text(about["credential_tag"])}</span>
            <div class="credentials-bar">
              <a href="{esc(about["logo_1_url"])}" target="_blank" rel="noopener"><img src="{esc(about["logo_1_image"])}" alt="{esc(about["logo_1_alt"])}"></a>
              <a href="{esc(about["logo_2_url"])}" target="_blank" rel="noopener"><img src="{esc(about["logo_2_image"])}" alt="{esc(about["logo_2_alt"])}"></a>
            </div>
          </div>
          <h2>{text(about["heading"])}</h2>
          <p class="subtitle">{text(about["subtitle"])}</p>
          <p>{text(about["bio"])}</p>
          <div class="cta-wrapper">
            {button(about["button"])}
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ====== STAT BAR ====== -->
  <div class="container">
    <div class="stat-bar">
{stats}
    </div>
  </div>

  <!-- ====== WHO THIS IS FOR ====== -->
  <section class="section">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["who_for"]["label"])}</span>
        <h2>{text(page["who_for"]["heading"])}</h2>
        <p>{text(page["who_for"]["description"])}</p>
      </div>
      <div class="symptoms-grid">
{symptoms}
      </div>
      <p class="text-center mt-4 section-footnote">{text(page["who_for"]["footnote"])}</p>
    </div>
  </section>

  <!-- ====== WHY THIS WORKS ====== -->
  <section class="section section-dark">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["why_works"]["label"])}</span>
        <h2>{text(page["why_works"]["heading"])}</h2>
        <p>{text(page["why_works"]["description"])}</p>
      </div>
      <div class="diff-grid">
{cards}
      </div>
    </div>
  </section>

{cta(page["cta"])}"""


def render_program(page: dict[str, Any], site: dict[str, Any]) -> str:
    components = "\n".join(
        f"""        <div class="benefit-card">
          <h4><span class="icon">{item["icon"]}</span> {text(item["title"])}</h4>
          <p>{text(item["text"])}</p>
        </div>"""
        for item in page["components"]["items"]
    )
    steps = "\n".join(
        f"""        <div class="step">
          <div class="step-number">{i}</div>
          <div class="step-content">
            <h4>{text(item["title"])}</h4>
            <p>{text(item["text"])}</p>
          </div>
        </div>"""
        for i, item in enumerate(page["steps"]["items"], start=1)
    )
    note_paras = "\n".join(f"        <p>{text(p)}</p>" for p in page["note"]["paragraphs"])
    return f"""{page_header(page["page_header"])}

  <!-- ====== WHAT WE PROVIDE ====== -->
  <section class="section">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["components"]["label"])}</span>
        <h2>{text(page["components"]["heading"])}</h2>
        <p>{text(page["components"]["description"])}</p>
      </div>
      <div class="benefits-grid">
{components}
      </div>
      <p class="text-center mt-4 section-footnote" style="font-size:0.95rem;">{text(page["components"]["footnote"])}</p>
    </div>
  </section>

  <!-- ====== HOW IT WORKS ====== -->
  <section class="section section-cream">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["steps"]["label"])}</span>
        <h2>{text(page["steps"]["heading"])}</h2>
      </div>
      <div class="steps">
{steps}
      </div>
    </div>
  </section>

  <!-- ====== IMPORTANT NOTE ====== -->
  <section class="section note-section">
    <div class="container">
      <div class="callout">
        <h4>{text(page["note"]["heading"])}</h4>
{note_paras}
      </div>
    </div>
  </section>

{cta(page["cta"])}"""


def render_why_cbti(page: dict[str, Any], site: dict[str, Any]) -> str:
    cards = []
    for item in page["root_cause"]["cards"]:
        list_html = ""
        if "bullets" in item:
            list_html = "\n          <ul>\n" + "\n".join(f"            <li>{text(b)}</li>" for b in item["bullets"]) + "\n          </ul>"
        cards.append(f"""        <div class="benefit-card">
          <h4><span class="icon">{item["icon"]}</span> {text(item["title"])}</h4>
          <p>{text(item["text"])}</p>{list_html}
        </div>""")
    ot_section_html = ""
    if "ot_diff" in page:
        ot = page["ot_diff"]
        ot_cards = "\n".join(
            f"""        <div class="benefit-card">
          <h4><span class="icon">{item["icon"]}</span> {text(item["title"])}</h4>
          <p>{text(item["text"])}</p>
        </div>"""
            for item in ot["cards"]
        )
        ot_section_html = f"""

  <!-- ====== OT-DRIVEN CBT-I ====== -->
  <section class="section section-dark">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(ot["label"])}</span>
        <h2>{text(ot["heading"])}</h2>
        <p>{text(ot["description"])}</p>
      </div>
      <div class="benefits-grid">
{ot_cards}
      </div>
    </div>
  </section>"""
    rows = "\n".join(
        f"""            <tr>
              <td>{text(item["factor"])}</td>
              <td class="check">&#10003;</td>
              <td class="cross">&#10007;</td>
            </tr>"""
        for item in page["comparison"]["rows"]
    )
    return f"""{page_header(page["page_header"])}

  <!-- ====== KEY POINT: ROOT CAUSE ====== -->
  <section class="section">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["root_cause"]["label"])}</span>
        <h2>{text(page["root_cause"]["heading"])}</h2>
        <p>{text(page["root_cause"]["description"])}</p>
      </div>
      <div class="benefits-grid">
{chr(10).join(cards)}
      </div>
    </div>
  </section>{ot_section_html}

  <!-- ====== COMPARISON ====== -->
  <section class="section section-cream">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["comparison"]["label"])}</span>
        <h2>{text(page["comparison"]["heading"])}</h2>
      </div>
      <div style="max-width:760px;margin:0 auto;">
        <table class="comparison-table">
          <caption class="sr-only">{text(page["comparison"]["caption"])}</caption>
          <thead>
            <tr>
              <th></th>
              <th class="highlight">{text(page["comparison"]["column_1"])}</th>
              <th class="muted">{text(page["comparison"]["column_2"])}</th>
            </tr>
          </thead>
          <tbody>
{rows}
          </tbody>
        </table>
      </div>
    </div>
  </section>

{cta(page["cta"])}"""


def render_about(page: dict[str, Any], site: dict[str, Any]) -> str:
    philosophy = "\n".join(f"        <p>{text(p)}</p>" for p in page["philosophy"]["paragraphs"])
    return f"""{page_header(page["page_header"])}

  <!-- ====== ABOUT ====== -->
{about_block(page["bio"])}

  <!-- ====== PHILOSOPHY ====== -->
  <section class="section section-cream">
    <div class="container">
      <div class="section-header">
        <span class="section-label">{text(page["philosophy"]["label"])}</span>
        <h2>{text(page["philosophy"]["heading"])}</h2>
      </div>
      <div class="prose-block">
{philosophy}
      </div>
    </div>
  </section>

{cta(page["cta"])}"""


def render_testimonials(page: dict[str, Any], site: dict[str, Any]) -> str:
    testimonials = "\n".join(
        f"""        <div class="testimonial-card">
          <div class="stars">{' '.join(['&#9733;'] * item["rating"])}</div>
          <blockquote>"{text(item["quote"])}"</blockquote>
          <div class="testimonial-author">
            <img src="{esc(item["image"])}" alt="{esc(item["image_alt"])}">
            <span class="testimonial-author-name">{text(item["author"])}</span>
          </div>
        </div>"""
        for item in page["testimonials"]
    )
    return f"""{page_header(page["page_header"])}

  <!-- ====== TESTIMONIALS ====== -->
  <section class="section">
    <div class="container">
      <div class="testimonials-grid">
{testimonials}
      </div>

      <div style="max-width:600px;margin:64px auto 0;text-align:center;">
        <div class="social-proof">
          <div style="text-align:left;">
            <strong class="strong">{text(page["social_proof"]["strong"])}</strong>
            <span>{text(page["social_proof"]["text"])}</span>
          </div>
        </div>
      </div>

      <p class="privacy-note">{text(page["privacy_note"])}</p>
    </div>
  </section>

{cta(page["cta"])}"""


def render_faqs(page: dict[str, Any], site: dict[str, Any]) -> str:
    items = []
    for item in page["questions"]:
        items.append(f"""        <div class="faq-item">
          <button class="faq-question" aria-expanded="false" onclick="this.parentElement.classList.toggle('open');this.setAttribute('aria-expanded',this.parentElement.classList.contains('open'))">
            {text(item["question"])}
            <span class="faq-toggle">+</span>
          </button>
          <div class="faq-answer">
{paragraphs(item["answer"])}
          </div>
        </div>""")
    return f"""{page_header(page["page_header"])}

  <!-- ====== FAQ LIST ====== -->
  <section class="section">
    <div class="container">
      <div class="faq-list">
{chr(10).join(items)}
      </div>
    </div>
  </section>

{cta(page["cta"])}"""


def render_contact(page: dict[str, Any], site: dict[str, Any]) -> str:
    contact = site["contact"]
    options = "\n".join(f'                <option value="{esc(option)}">{text(option)}</option>' for option in page["form"]["concern_options"])
    return f"""{page_header(page["page_header"])}

  <!-- ====== CONTACT ====== -->
  <section class="section">
    <div class="container">
      <div class="contact-grid">
        <div class="contact-info">
          <h2>{text(page["reach_out"]["heading"])}</h2>
          <p>{text(page["reach_out"]["description"])}</p>

          <div class="contact-detail">
            <div class="icon-box">&#9993;</div>
            <div class="detail-text">
              <strong>Email</strong>
              <a href="mailto:{esc(contact["email"])}">{text(contact["email"])}</a>
            </div>
          </div>

          <div class="contact-detail">
            <div class="icon-box">&#9742;</div>
            <div class="detail-text">
              <strong>Phone</strong>
              <a href="{esc(contact["phone_href"])}">{text(contact["phone_display"])}</a>
            </div>
          </div>

          <div class="contact-detail">
            <div class="icon-box">&#9733;</div>
            <div class="detail-text">
              <strong>Payment</strong>
              <span>{text(contact["payment"])}</span>
            </div>
          </div>

          <div class="info-callout">
            <h4>{text(page["expect"]["heading"])}</h4>
            <p>{text(page["expect"]["text"])}</p>
          </div>
        </div>

        <div class="contact-form">
          <h3>{text(page["form"]["heading"])}</h3>
          <form id="contact-form" onsubmit="return sendMail()">
            <div class="form-row">
              <div class="form-group">
                <label for="first-name">{text(page["form"]["first_name"])}</label>
                <input type="text" id="first-name" required aria-label="First name">
              </div>
              <div class="form-group">
                <label for="last-name">{text(page["form"]["last_name"])}</label>
                <input type="text" id="last-name" required aria-label="Last name">
              </div>
            </div>
            <div class="form-group">
              <label for="email">{text(page["form"]["email"])}</label>
              <input type="email" id="email" required aria-label="Email address">
            </div>
            <div class="form-group">
              <label for="phone">{text(page["form"]["phone"])}</label>
              <input type="tel" id="phone" required aria-label="Phone number">
            </div>
            <div class="form-group">
              <label for="concern">{text(page["form"]["concern"])}</label>
              <select id="concern" aria-label="Primary concern">
                <option value="">{text(page["form"]["concern_placeholder"])}</option>
{options}
              </select>
            </div>
            <div class="form-group">
              <label for="message">{text(page["form"]["message_label"])}</label>
              <textarea id="message" placeholder="{esc(page["form"]["message_placeholder"])}" aria-label="Tell us about your sleep"></textarea>
            </div>
            <button type="submit" class="btn btn-primary">{text(page["form"]["submit"])}</button>
          </form>
          <div id="form-confirmation" style="display:none;text-align:center;padding:48px 24px;">
            <div style="font-size:2.5rem;margin-bottom:16px;">&#9993;</div>
            <h3 style="margin-bottom:12px;">{text(page["confirmation"]["heading"])}</h3>
            <p style="color:var(--text-light);max-width:400px;margin:0 auto 24px;">{text(page["confirmation"]["text_prefix"])} <strong>{text(page["confirmation"]["strong"])}</strong> {text(page["confirmation"]["text_suffix"])}</p>
            <p style="font-size:0.85rem;color:var(--light-gray);">{text(page["confirmation"]["fallback_prefix"])} <a href="mailto:{esc(contact["email"])}" style="color:var(--turquoise);">{text(page["confirmation"]["fallback_link"])}</a></p>
          </div>
          <script>
            function sendMail() {{
              var firstName = document.getElementById('first-name').value.trim();
              var lastName = document.getElementById('last-name').value.trim();
              var email = document.getElementById('email').value.trim();
              var phone = document.getElementById('phone').value.trim();
              var concern = document.getElementById('concern').value;
              var message = document.getElementById('message').value.trim();

              var emailPattern = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
              if (!emailPattern.test(email)) {{
                alert('Please enter a valid email address.');
                document.getElementById('email').focus();
                return false;
              }}

              var phoneClean = phone.replace(/[\\s\\-\\(\\)\\.]/g, '');
              if (!/^\\+?\\d{{10,15}}$/.test(phoneClean)) {{
                alert('Please enter a valid phone number (10-15 digits).');
                document.getElementById('phone').focus();
                return false;
              }}

              var subject = 'CBT-I Inquiry from ' + firstName + ' ' + lastName;

              var body = 'Dear Tierza,\\n\\n';
              if (concern) {{
                body += 'Concern: ' + concern + '.\\n\\n';
              }}
              if (message) {{
                body += message + '\\n\\n';
              }}
              body += firstName + ' ' + lastName + '\\n';
              body += email + '\\n';
              body += phone;

              window.location.href = 'mailto:{esc(contact["email"])}'
                + '?subject=' + encodeURIComponent(subject)
                + '&body=' + encodeURIComponent(body);

              document.getElementById('form-confirmation').style.display = 'block';
              document.getElementById('contact-form').style.display = 'none';

              return false;
            }}
          </script>
        </div>
      </div>
    </div>
  </section>"""


RENDERERS = {
    "home": render_home,
    "program": render_program,
    "why_cbti": render_why_cbti,
    "about": render_about,
    "testimonials": render_testimonials,
    "faqs": render_faqs,
    "contact": render_contact,
}


def render_page(page_key: str, data: dict[str, Any]) -> str:
    site = data["site"]
    page = data["pages"][page_key]
    body = RENDERERS[page_key](page, site)
    return f"""<!DOCTYPE html>
<html lang="en">
{head(page_key, page, site)}
<body>

{header(page_key, site)}

  <main>
{body}
  </main>

{footer(site)}

  <script>
    const header = document.getElementById('site-header');
    window.addEventListener('scroll', () => header.classList.toggle('scrolled', window.scrollY > 40));
    document.getElementById('nav-toggle').addEventListener('click', () => document.getElementById('nav-links').classList.toggle('open'));
  </script>
</body>
</html>
"""


def generate(data: dict[str, Any], output_dir: Path) -> dict[Path, str]:
    return {output_dir / PAGE_FILES[key]: render_page(key, data) for key in PAGE_ORDER}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Insomnia Warriors HTML pages from contents-codex.md")
    parser.add_argument("--content", type=Path, default=CONTENT_FILE, help="Path to content Markdown file")
    parser.add_argument("--output-dir", type=Path, default=ROOT, help="Directory for generated HTML files")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated pages differ from files on disk")
    args = parser.parse_args()

    data = parse_input_file(args.content)
    generated = generate(data, args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.check:
        changed = [path for path, content in generated.items() if not path.exists() or path.read_text(encoding="utf-8") != content]
        if changed:
            for path in changed:
                print(f"out of date: {display_path(path)}", file=sys.stderr)
            return 1
        print("All generated HTML pages are up to date.")
        return 0

    for path, content in generated.items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {display_path(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
