# lixSearch Now Supports PDF Export

**March 2026** | Product Update

## Export Any Answer as a Professional PDF

lixSearch now lets you export any search response directly as a beautifully formatted PDF document. Whether you're compiling research, saving reference material, or sharing findings with your team, you can now get a downloadable PDF with a single request.

## How It Works

When you ask lixSearch a question and want the answer as a PDF, simply ask it to "export this as a PDF" or "save this as a PDF." The AI will automatically generate a professionally branded document with:

- **Branded header and footer** with lixSearch branding and page numbers
- **Clean typography** with proper heading hierarchy, bullet points, and paragraph spacing
- **Source citations** preserved from the original search results
- **Smart filenames** derived from the content title rather than random IDs
- **7-day availability** via a shareable URL at `/api/content/<id>`

## For API Users

If you're using the lixSearch API (or the OpenAI-compatible `/v1/chat/completions` endpoint), the `export_to_pdf` tool is available to the model automatically. The model will call it when appropriate and include the download URL in its response.

You can also use the direct export endpoint:

```
POST /api/export/pdf
Content-Type: application/json

{
  "content": "Your markdown content here...",
  "title": "Document Title"
}
```

This returns the PDF bytes directly as a download.

Generated PDFs are served at:

```
GET /api/content/<content-id>
```

## For Pollinations Users

If you're accessing lixSearch through the Pollinations API, PDF export works seamlessly. Just ask the model to export your results as a PDF, and you'll receive a direct download link in the response.

## What's Next

This is part of our ongoing work to make lixSearch production-grade for API consumers. Coming up:

- Batch export of multi-turn conversations
- Custom branding options for enterprise users
- HTML and DOCX export formats

---

*lixSearch is an open-source intelligent search assistant. Learn more at [search.elixpo.com](https://search.elixpo.com).*
