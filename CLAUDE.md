# Insomnia Warriors — Website

## What This Is
Professional website for **Insomnia Warriors**, a CBT-I (Cognitive Behavioral Therapy for Insomnia) practice run by **Tierza Clerc, OTR/L, CBT-I Certified**. Static HTML/CSS site hosted on GitHub Pages.

**Live URL:** https://insomniawarriors.com/

## Tech Stack
- Static HTML + CSS (no build tools, no framework)
- Google Fonts: Poppins (body) + Manrope (headings)
- Two-color brand palette: turquoise (`#6CEDEF`) + white, with dark grays for text
- CSS custom properties defined in `:root` of `styles.css`
- No JavaScript dependencies — vanilla JS only (header scroll, mobile nav toggle, mailto form)

## File Structure
```
├── index.html          # Homepage
├── program.html        # The Program (treatment details)
├── why-cbti.html       # Why CBT-I (evidence, comparison table)
├── about.html          # Meet Tierza (bio, credentials, philosophy)
├── testimonials.html   # Client testimonials (3 reviews)
├── faqs.html           # FAQs (9 accordion items)
├── contact.html        # Contact form (mailto-based, no backend)
├── styles.css          # Single stylesheet for all pages
├── contents.md         # Content mirror for non-technical editing (keep in sync with HTML)
├── sitemap.xml         # SEO sitemap
├── robots.txt          # Crawler permissions (allows AI bots)
├── llms.txt            # AI agent discovery file
├── images/             # All site images
│   ├── logo.png        # Main logo (250x250, warrior+moon+text)
│   ├── favicons/       # Generated from logo (warrior+moon only, no text)
│   ├── tierza-clerc.png
│   ├── uw-medicine.png
│   ├── colorado-state.png
│   └── testimonial-*.{png,jpg}
└── google1dba84cb7f2f1233.html  # Google Search Console verification
```

## Important Conventions
- **Every HTML page** shares the same header nav and footer. Changes to nav/footer must be applied to all 7 pages.
- **Schema.org JSON-LD** structured data is in each page's `<head>` — keep it accurate when content changes.
- **contents.md** is the single source of truth for website copy. When editing text, update both the HTML file and contents.md to maintain the 1:1 relationship.
- **Favicons** were generated from the logo with text removed (warrior+moon icon only). Source images are in `images/favicons/`.
- Contact form uses `mailto:` URI — no server-side form handling. The `sendMail()` function builds the email and opens the user's email client.

## SEO & Discoverability
- All pages have Open Graph meta tags and JSON-LD structured data
- `sitemap.xml` lists all 7 pages
- `robots.txt` explicitly allows AI bots (GPTBot, ClaudeBot, PerplexityBot)
- `llms.txt` provides plain-text summary for AI agents

## Contact Info
- Email: insomniawarriors@pm.me
- Phone: (253) 223-1751
- HSA/FSA accepted, superbills provided, no insurance billing

## Pending / Known Issues
- Future: consider regenerating the ICO with BMP-encoded frames if older browser support becomes important. Current pages prefer PNG favicons and keep the ICO as a fallback.
- Future: build a script to auto-sync contents.md ↔ HTML files (brainstorm stage).
